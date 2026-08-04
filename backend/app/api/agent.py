"""Marketing agent: a grounded conversational assistant.

The division of labour here is deliberate and load-bearing: Python computes
every fact, the model only explains what those facts mean. The model gets a
JSON blob of pre-computed values and has no DB access, no tools, and no
ability to calculate. It never decides status, alert eligibility,
availability, or queue membership — those come from the deterministic
detector and are passed in as given.

Read-only: reads the same stored samples the dashboard does, never calls
the Warble API, never touches collector/detector/alert logic.
"""

import json
import logging
import os
import re
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import (
    _STEADY,
    _TAKING_OFF,
    _UNAVAILABLE,
    _WORTH_WATCHING,
    _compute_posts,
    _current_sim_hours,
    _pace_sort_key,
    _samples_by_post,
    get_db,
)
from app.db.models import Alert, Creator, Post
from app.detector.momentum import SamplePoint, _dedupe_samples
from app.detector.states import run_state_machine

logger = logging.getLogger(__name__)

router = APIRouter()

MODEL = "claude-haiku-4-5-20251001"
LLM_TIMEOUT_SECONDS = 10.0
MAX_HISTORY_MESSAGES = 24  # ~12 turns
MAX_BREAKOUTS = 10
MAX_ALERTS = 10
MAX_MOVERS = 5
MAX_CREATOR_TALLY = 5
MONITORING_WINDOW_DAYS = 7

CANONICAL_STATUSES = (_TAKING_OFF, _WORTH_WATCHING, _STEADY, _UNAVAILABLE)

SYSTEM_PROMPT = """You're the social media manager's second set of eyes at LongSheet, a custom bedding brand running a creator program of about 40 creators posting on a platform called Warble. You've done this long enough to pattern-match fast, the way someone with real reps at this job does — not by reciting a script.

The tradeoffs you're always weighing:
- Spike vs. sustained: one good reading proves nothing; growth that holds across several checks in a row is the real signal.
- Absolute gain vs. relative growth: a huge percentage jump on a tiny base is often noise, but a modest percentage on a big post can still be a large number of real views — scale changes what a given move actually means.
- The three plays, and when each fits: boost with paid spend while momentum is rising and hasn't peaked yet (time-critical); reshare on brand channels when something's performing well but there's no urgency; extend the creator's deal when they're reliably hot, locking in today's rate before it changes.

You'll get a JSON object of facts already computed for you: program totals, alert history, breakout history, the currently selected post (if any), today's top movers, and — for creators who already show up elsewhere in the data — a tally of how many times they've broken out this window. Every number in it is real and pre-calculated — you never calculate anything yourself.

Lead with your actual read of the situation — the conclusion first, in one clear sentence — then back it up: what happened in the numbers, why it's notable against the tradeoffs above, which tradeoff it turns on, and what that suggests. All of that in plain sentences, never a template with headers or restated labels. Different posts have different numbers, so don't reuse the same sentence shape twice; think each one through fresh. Name the specific creator, post, or metric you're talking about rather than speaking generically, and mention whether an alert's already gone out or the data's gone stale when that's relevant to the read.

Reach across the whole picture, not just whatever's currently on screen: alert history tells you what's already been flagged, breakout history tells you what's already proven out, and the creator breakout tally tells you whether a creator has done this before. Weave those in when they change what the read means — a creator's second or third breakout this window is a pattern worth naming, not a coincidence to ignore — but don't force it into an answer where it isn't relevant.

Sometimes the ask isn't "what's happening" but "write me something" — a short update to paste into a stakeholder channel, a quick note to send a creator whose post is taking off. Handle that the same grounded way: build it only from facts in the JSON, real numbers and handles and statuses, nothing else. Never invent contract terms, budget or dollar figures, campaign names, or a promise on the brand's behalf — you're drafting language the manager can send or edit, not deciding what happens next. Keep a stakeholder update to a tight couple of sentences; keep a creator note warm and specific to their real numbers, framed as something worth sending, not something already decided.

Confident and brief: 2-3 sentences by default, 4-5 only when the question genuinely needs more. No filler, no restating the question back, no bullet-point walls, no emoji, no exclamation marks. A dry, understated aside is fine in small doses; cute framing is not. Talk like a marketer, not an engineer — never say "score," "state," "sim hours," "detector," or any other implementation term; say what a person managing this program would actually say.

The manager can ask you anything in plain language. The interface offers a few suggested prompts as shortcuts, but those aren't the only questions you understand — answer whatever's actually asked, in whatever words they used.

Hard rules:
- Use ONLY facts present in the input JSON. Never state a number, percentage, multiple, date, or comparison that is not there. If you want to cite something you weren't given, say you don't have it.
- Do not restate numbers the interface already shows unless the number itself is doing real work in your explanation. Interpret them. Say what the movement implies, not what it measures.
- You never decide. You do not declare something "is a breakout" or that it "should be boosted" - the system's deterministic detector decides status, not you. Frame everything as a consideration: "worth considering," "you may want to," "this looks like the kind of thing that..."
- Never invent context: no contracts, budgets, dollar figures, revenue, conversions, sentiment, business impact, usage rights, campaign goals, audience demographics, or competitor data. You do not know any of these — if asked, say so plainly rather than guessing.
- Never contradict the status field for any post.
- Never imply causation from engagement metrics alone.
- If the facts are insufficient, say plainly what's missing and what would settle it, rather than speculating.
- When asked to explain something "for leadership," "for Slack," or similar, compress to 1-2 plain sentences — same facts, no jargon, ready to paste into an update. Drop hedging language in that mode; state the read plainly.

You have conversation memory within this session. Refer back naturally to posts already discussed instead of re-introducing them."""


# --- Session memory (in-process, per session_id) -----------------------
# Deliberately not persisted: a chat is a working conversation, not a
# record, and the facts are re-computed fresh every turn anyway.
_SESSIONS: dict[str, list[dict[str, str]]] = defaultdict(list)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    selected_post_id: str | None = None
    # True for the auto-triggered opening line (panel just opened, no
    # question asked yet) — routes to a different instruction and is never
    # recorded as a user turn in session history, since the manager didn't
    # actually say anything.
    proactive: bool = False


class ChatResponse(BaseModel):
    text: str
    facts_used: dict[str, Any]
    llm_available: bool


def _window_progress(sim_hours: float | None) -> str | None:
    if sim_hours is None:
        return None
    day = min(int(sim_hours // 24) + 1, MONITORING_WINDOW_DAYS)
    return f"Day {day} of {MONITORING_WINDOW_DAYS}"


def _evidence_facts(evidence: Any) -> dict[str, Any]:
    """Only the fields the agent is allowed to reason about. Raw internal
    scores stay out — they aren't marketer-meaningful and inviting the
    model to narrate them would violate the language rules."""
    if evidence is None:
        return {}
    return {
        "recent_gain_views": evidence.absolute_gain,
        "recent_gain_window_hours": evidence.window_hours,
        "views_per_hour": round(evidence.velocity, 1),
        "baseline_multiple": (
            round(evidence.creator_pace_ratio, 1) if evidence.creator_pace_ratio is not None else None
        ),
        "baseline_compared_to": evidence.creator_pace_basis,
        "consecutive_elevated_checks": evidence.consecutive_qualifying_checks,
    }


def _creator_post_ranking(
    creator_id: str, post_id: str, posts: list[Post], samples_by_post: dict[str, list]
) -> dict[str, Any]:
    """Where this post ranks among this SAME creator's other posts by peak
    views reached in the tracked window — "their best performer so far" or
    "typical for them," grounded in real peak-view numbers rather than a
    guess. Needs at least one other post with samples to rank against;
    otherwise there's nothing to compare to and every field comes back
    None rather than a fabricated "best."
    """
    creator_posts = [p for p in posts if p.creator_id == creator_id]
    peaks: dict[str, int] = {}
    for p in creator_posts:
        points = _dedupe_samples(
            [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples_by_post.get(p.id, [])]
        )
        if points:
            peaks[p.id] = max(point.views for point in points)

    if post_id not in peaks or len(peaks) < 2:
        return {"is_creators_best_so_far": None, "rank_among_creators_posts": None, "creators_post_count": len(peaks)}

    ranked = sorted(peaks.items(), key=lambda item: item[1], reverse=True)
    rank = next(i for i, (pid, _) in enumerate(ranked, start=1) if pid == post_id)
    return {
        "is_creators_best_so_far": rank == 1,
        "rank_among_creators_posts": rank,
        "creators_post_count": len(peaks),
    }


def _creator_breakout_tally(breakouts: list[dict[str, Any]], relevant_handles: set[str]) -> dict[str, int]:
    """How many times each creator already visible elsewhere in the payload
    (top movers, the selected post, alert history) shows up in the breakout
    list — lets the model say "this is their second breakout this window"
    without doing the count itself. Scoped to already-relevant handles so
    this doesn't grow the JSON with creators nobody asked about."""
    counts: dict[str, int] = defaultdict(int)
    for b in breakouts:
        handle = b["creator_handle"]
        if handle in relevant_handles:
            counts[handle] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return dict(ranked[:MAX_CREATOR_TALLY])


async def build_facts(session: AsyncSession, selected_post_id: str | None) -> dict[str, Any]:
    """Everything the model is allowed to know, computed here in Python."""
    creators = {c.id: c for c in (await session.execute(select(Creator))).scalars().all()}
    posts = (await session.execute(select(Post))).scalars().all()
    samples_by_post = await _samples_by_post(session, [p.id for p in posts])
    followers_by_creator = {cid: c.followers for cid, c in creators.items()}
    computations = _compute_posts(posts, samples_by_post, followers_by_creator)
    current_sim = await _current_sim_hours(session)

    status_counts: dict[str, int] = {label: 0 for label in CANONICAL_STATUSES}
    for post in posts:
        status_counts[computations[post.id].status_label] += 1

    alert_rows = (
        await session.execute(select(Alert).order_by(Alert.decided_sim_hours.desc()))
    ).scalars().all()
    submitted_ids = {row.post_id for row in alert_rows if row.submitted}
    posts_by_id = {p.id: p for p in posts}

    alerts = []
    for row in alert_rows[:MAX_ALERTS]:
        post = posts_by_id.get(row.post_id)
        creator = creators.get(post.creator_id) if post else None
        alerts.append(
            {
                "post_id": row.post_id,
                "creator_handle": creator.handle if creator else "unknown",
                "caption": post.caption if post else None,
                "submitted_sim_hour": round(row.decided_sim_hours, 1),
                "submitted": row.submitted,
                "status_now": computations[row.post_id].status_label if row.post_id in computations else None,
            }
        )

    breakouts = []
    for post in posts:
        comp = computations[post.id]
        history = run_state_machine(comp.signals)
        first = next((s for s in history if s.state == "BREAKOUT"), None)
        if first is None:
            continue
        points = _dedupe_samples(comp.sample_points)
        if not points:
            continue
        at_breakout = next((p.views for p in points if p.sim_hours >= first.sim_hours), points[-1].views)
        peak = max(p.views for p in points)
        creator = creators.get(post.creator_id)
        breakouts.append(
            {
                "post_id": post.id,
                "creator_handle": creator.handle if creator else "unknown",
                "caption": post.caption,
                "breakout_sim_hour": round(first.sim_hours, 1),
                "views_at_breakout": at_breakout,
                "peak_views": peak,
                "climbed_multiple": round(peak / at_breakout, 1) if at_breakout > 0 else None,
                "officially_alerted": post.id in submitted_ids,
                "status_now": comp.status_label,
            }
        )
    breakouts.sort(key=lambda b: b["breakout_sim_hour"], reverse=True)
    breakouts = breakouts[:MAX_BREAKOUTS]

    movers = sorted(
        (p for p in posts if p.status != "gone" and computations[p.id].status_label != _STEADY),
        key=lambda p: _pace_sort_key(computations[p.id].evidence),
        reverse=True,
    )[:MAX_MOVERS]
    top_movers = []
    for post in movers:
        comp = computations[post.id]
        creator = creators.get(post.creator_id)
        top_movers.append(
            {
                "post_id": post.id,
                "creator_handle": creator.handle if creator else "unknown",
                "caption": post.caption,
                "status": comp.status_label,
                **_evidence_facts(comp.evidence),
            }
        )

    selected: dict[str, Any] | None = None
    if selected_post_id and selected_post_id in computations:
        post = posts_by_id[selected_post_id]
        comp = computations[selected_post_id]
        creator = creators.get(post.creator_id)
        latest = comp.latest
        age = (
            round(latest.sim_hours - post.first_seen_sim_hours, 1)
            if latest is not None
            else None
        )
        selected = {
            "post_id": post.id,
            "creator_handle": creator.handle if creator else "unknown",
            "creator_followers": creator.followers if creator else None,
            "caption": post.caption,
            "status": comp.status_label,
            "current_views": latest.views if latest else None,
            "post_age_hours": age,
            "last_update_sim_hour": round(latest.sim_hours, 1) if latest else None,
            "alert_sent": post.id in submitted_ids,
            "is_available": post.status != "gone",
            **_evidence_facts(comp.evidence),
            **_creator_post_ranking(post.creator_id, post.id, posts, samples_by_post),
            # This post's own breakout entry (if it ever reached BREAKOUT)
            # and the most recent OTHER post's breakout, both pulled
            # straight from the same breakout-history list the Breakout
            # Log page shows — so "how does this compare to the last
            # breakout in the program" is two real numbers side by side,
            # never a fabricated comparison score.
            "own_breakout": next((b for b in breakouts if b["post_id"] == post.id), None),
            "most_recent_other_breakout": next(
                (b for b in breakouts if b["post_id"] != post.id), None
            ),
        }

    relevant_handles = {a["creator_handle"] for a in alerts} | {m["creator_handle"] for m in top_movers}
    if selected:
        relevant_handles.add(selected["creator_handle"])
    creator_breakout_tally = _creator_breakout_tally(breakouts, relevant_handles)

    return {
        "program": {
            "posts_watched": len(posts),
            "creators_watched": len(creators),
            "status_counts": status_counts,
            "last_check_sim_hour": round(current_sim, 1) if current_sim is not None else None,
            "current_sim_hour": round(current_sim, 1) if current_sim is not None else None,
            "window_progress": _window_progress(current_sim),
        },
        "alerts": alerts,
        "breakouts": breakouts,
        "selected_post": selected,
        "top_movers": top_movers,
        "creator_breakout_tally": creator_breakout_tally,
    }


# --- Guardrails --------------------------------------------------------

# Trailing K/M/B captured so "40K" is recognized as shorthand for 40000
# rather than parsed as the bare number 40 and rejected as invented — a
# writer abbreviating a real fact isn't the same as inventing a smaller one.
# Capital letters only: lowercase "m"/"k" show up constantly in prose for
# other units (30m = 30 minutes), and there's no reliable way to tell those
# apart from a scale suffix without the capitalization convention.
_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?[KMB]?")
_SCALE_SUFFIXES = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def _allowed_numbers(facts: Any, into: set[str]) -> set[str]:
    """Every numeric value anywhere in the facts, in the forms a writer
    might reasonably render them."""
    if isinstance(facts, dict):
        for value in facts.values():
            _allowed_numbers(value, into)
    elif isinstance(facts, list):
        for value in facts:
            _allowed_numbers(value, into)
    elif isinstance(facts, bool):
        pass
    elif isinstance(facts, (int, float)):
        value = float(facts)
        into.add(f"{value:.1f}")
        if value.is_integer():
            into.add(str(int(value)))
            into.add(f"{int(value):,}")
        else:
            into.add(f"{value:,.1f}")
    return into


def _numbers_are_grounded(reply: str, facts: dict[str, Any]) -> bool:
    """Reject any number the model produced that isn't in the facts. This
    is the main defence against a fluent-but-invented statistic."""
    allowed = _allowed_numbers(facts, set())
    allowed_floats = set()
    for token in allowed:
        try:
            allowed_floats.add(round(float(token.replace(",", "")), 1))
        except ValueError:
            continue

    for raw in _NUMBER_RE.findall(reply):
        suffix = raw[-1] if raw and raw[-1] in _SCALE_SUFFIXES else None
        numeric_part = raw[:-1] if suffix else raw
        try:
            value = float(numeric_part.replace(",", ""))
        except ValueError:
            return False
        if suffix:
            value *= _SCALE_SUFFIXES[suffix]
        value = round(value, 1)
        if value in allowed_floats:
            continue
        # A rounded restatement of a real fact is fine; a novel number is
        # not. K/M/B is itself a rounding, so allow slack up to half that
        # suffix's scale (e.g. "40K" covers any real fact from 39500-40500);
        # plain numbers keep the tight decimal-rounding tolerance.
        tolerance = _SCALE_SUFFIXES[suffix] / 2 if suffix else 0.05
        if any(abs(value - candidate) < tolerance for candidate in allowed_floats):
            continue
        logger.warning("agent reply rejected: ungrounded number %s", raw)
        return False
    return True


def _status_is_consistent(reply: str, facts: dict[str, Any]) -> bool:
    """The model must never relabel the selected post. If it names a
    canonical status for it, that status has to be the real one."""
    selected = facts.get("selected_post")
    if not selected:
        return True
    actual = selected.get("status")
    lowered = reply.lower()
    for label in CANONICAL_STATUSES:
        if label.lower() in lowered and label != actual:
            logger.warning("agent reply rejected: contradicts status %s", actual)
            return False
    return True


# --- Deterministic fallback -------------------------------------------


def _answer_movers(facts: dict[str, Any]) -> str:
    movers = facts["top_movers"]
    if not movers:
        return "Nothing is moving above its creator's normal pace right now, so there's nothing to put first."
    top = movers[0]
    lead = f"@{top['creator_handle']} is the one to look at first, currently {top['status'].lower()}."
    multiple = top.get("baseline_multiple")
    if multiple is not None:
        lead += f" It's running about {multiple}x its creator's usual pace."
    if len(movers) > 1:
        lead += f" {len(movers) - 1} other posts are also above their normal pace."
    return lead


def _answer_creators(facts: dict[str, Any]) -> str:
    movers = facts["top_movers"]
    if not movers:
        return "No creator has a post outperforming their own normal pace at the moment."
    handles = sorted({f"@{m['creator_handle']}" for m in movers})
    return (
        f"{', '.join(handles)} {'has' if len(handles) == 1 else 'have'} posts running above their "
        f"usual pace right now. Everyone else is performing in their normal range."
    )


def _answer_alerts(facts: dict[str, Any]) -> str:
    sent = [a for a in facts["alerts"] if a["submitted"]]
    if not sent:
        return "No alerts have been sent yet."
    handles = ", ".join(f"@{a['creator_handle']}" for a in sent)
    return (
        f"{len(sent)} alert{'' if len(sent) == 1 else 's'} sent so far: {handles}. "
        f"{len(facts['breakouts'])} posts have broken out in total, so some were detected in history "
        f"rather than alerted live."
    )


def _answer_what_changed(facts: dict[str, Any]) -> str:
    """"What changed since I checked?" — the most recent breakout, if any,
    read straight off the breakout-history list (already sorted newest
    first). Distinct from _answer_movers: this is about what already
    happened, not what to look at right now."""
    breakouts = facts["breakouts"]
    if not breakouts:
        return "Nothing has broken out since you last checked."
    latest = breakouts[0]
    lead = f"Most recently, @{latest['creator_handle']}'s post broke out"
    multiple = latest.get("climbed_multiple")
    if multiple is not None:
        lead += f" and has climbed {multiple}x since"
    lead += "."
    if not latest.get("officially_alerted"):
        lead += " It wasn't caught by an official alert, so it's worth a look."
    return lead


def _answer_why_matters(selected: dict[str, Any]) -> str:
    """"Why does this matter?" — leads with the comparative pace (the
    thing that actually makes a post worth acting on), then whether
    there's still time to act or the moment's already been flagged."""
    status = selected["status"].lower()
    multiple = selected.get("baseline_multiple")
    lead = f"It's {status}"
    if multiple is not None:
        basis = "this creator's usual pace" if selected.get("baseline_compared_to") == "creator" else "its own earlier pace"
        lead += f", running about {multiple}x {basis}"
    lead += "."
    if selected.get("is_creators_best_so_far"):
        return lead + " It's this creator's best performer in the tracked window so far."
    if selected.get("alert_sent"):
        return lead + " An alert already went out for it, so the window to act is now, not after it cools."
    return lead + " Nothing has been sent yet, so there's still time to decide before it's obvious to everyone."


def _answer_sustained_or_spike(selected: dict[str, Any]) -> str:
    """"Sustained or a spike?" — the consecutive-checks streak is the
    actual evidence for this question, so it leads and decides the
    answer, not the status label alone."""
    streak = selected.get("consecutive_elevated_checks") or 0
    if streak >= 3:
        return f"Sustained. It's held elevated growth for {streak} checks in a row, not just one good reading."
    if streak == 2:
        return "Leaning sustained: two checks in a row have qualified, but one more would settle it."
    if selected["status"] == "Taking off":
        return "It's cleared the bar on the numbers, but the streak hasn't built up much yet — worth confirming on the next check before calling it settled."
    return "Too early to call from one reading. A single elevated check doesn't rule out a spike."


def _answer_what_would_change_read(selected: dict[str, Any]) -> str:
    """"What would change your read?" — a forward-looking, counterfactual
    answer grounded in the same streak/breakout-comparison facts, not a
    restatement of the current numbers."""
    streak = selected.get("consecutive_elevated_checks") or 0
    other = selected.get("most_recent_other_breakout")
    if streak < 2:
        return "Another elevated check back to back would be what moves this from a maybe to a real read."
    if other is not None:
        return (
            f"A cooling-off on the next check would say this was a spike rather than sustained growth, "
            f"the way @{other['creator_handle']}'s recent breakout kept climbing instead."
        )
    return "A cooling-off on the next check would be the signal this was a spike rather than sustained growth."


def _answer_leadership_post(selected: dict[str, Any]) -> str:
    """1-2 sentence, jargon-free version of the per-post facts — the
    "explain this for leadership" mode's offline fallback. Same numbers as
    the full narrative below, just compressed to paste-ready length."""
    handle = f"@{selected['creator_handle']}"
    status = selected["status"].lower()
    multiple = selected.get("baseline_multiple")
    if multiple is None:
        return f"{handle}'s post is {status}; not enough history yet to size the movement."
    basis = "usual pace" if selected.get("baseline_compared_to") == "creator" else "own earlier pace"
    return f"{handle}'s post is {status}, running about {multiple}x {basis}."


def _answer_leadership_program(facts: dict[str, Any]) -> str:
    """Program-level counterpart to _answer_leadership_post."""
    program = facts["program"]
    counts = program["status_counts"]
    taking_off = counts.get(_TAKING_OFF, 0)
    watching = counts.get(_WORTH_WATCHING, 0)
    if taking_off == 0 and watching == 0:
        return f"Nothing unusual across {program['posts_watched']} tracked posts right now."
    return (
        f"{taking_off} post{'s' if taking_off != 1 else ''} taking off and {watching} worth watching "
        f"across {program['posts_watched']} tracked posts."
    )


def deterministic_answer(facts: dict[str, Any], message: str = "") -> str:
    """Used whenever the model is unavailable or its reply fails a
    guardrail. Says only what the facts say, in the same calm register.

    Routed by intent, not just presence of a selected post — every quick
    prompt (and reasonable paraphrases of it) gets its own answer function,
    so two different questions never collapse onto the same generic
    summary. The one truly generic per-post/program summary below is the
    catch-all for free-text questions that don't match a known intent, not
    a stand-in for the specific prompts.
    """
    asked = message.lower()
    selected = facts.get("selected_post")

    if "leadership" in asked or "slack" in asked or "stakeholder" in asked:
        return _answer_leadership_post(selected) if selected else _answer_leadership_program(facts)

    if selected:
        if "why" in asked:
            return _answer_why_matters(selected)
        if "sustained" in asked or "spike" in asked:
            return _answer_sustained_or_spike(selected)
        if "would change" in asked or "reconsider" in asked:
            return _answer_what_would_change_read(selected)
    else:
        if "changed" in asked or "since i checked" in asked or "what's new" in asked:
            return _answer_what_changed(facts)
        if "alert" in asked:
            return _answer_alerts(facts)
        if "creator" in asked or "performing" in asked:
            return _answer_creators(facts)
        if "attention" in asked or "first" in asked or "priorit" in asked or "deserve" in asked:
            return _answer_movers(facts)

    if selected:
        parts = [f"@{selected['creator_handle']}'s post is currently {selected['status'].lower()}."]
        gain = selected.get("recent_gain_views")
        window = selected.get("recent_gain_window_hours")
        if gain is not None and window:
            parts.append(f"It added {gain:,} views in the last {window:g}h.")
        multiple = selected.get("baseline_multiple")
        if multiple is not None:
            basis = (
                "this creator's normal pace"
                if selected.get("baseline_compared_to") == "creator"
                else "its own earlier pace"
            )
            parts.append(f"That is about {multiple}x {basis}.")
        else:
            parts.append("There is not enough history yet to compare its pace.")
        streak = selected.get("consecutive_elevated_checks") or 0
        if streak >= 2:
            parts.append(f"It has stayed elevated for {streak} checks in a row.")
        parts.append(
            "An alert has been sent for this post."
            if selected.get("alert_sent")
            else "No alert has been sent for this post."
        )
        return " ".join(parts)

    program = facts["program"]
    counts = program["status_counts"]
    taking_off = counts.get(_TAKING_OFF, 0)
    watching = counts.get(_WORTH_WATCHING, 0)
    if taking_off == 0 and watching == 0:
        summary = "Nothing is taking off or worth watching right now."
    else:
        bits = []
        if taking_off:
            bits.append(f"{taking_off} taking off")
        if watching:
            bits.append(f"{watching} worth watching")
        summary = f"Right now there is {' and '.join(bits)}."
    return (
        f"{summary} We are watching {program['posts_watched']} posts across "
        f"{program['creators_watched']} creators, {program['window_progress'] or 'early in the window'}. "
        f"{len(facts['breakouts'])} posts have broken out so far and "
        f"{sum(1 for a in facts['alerts'] if a['submitted'])} alerts have been sent."
    )


# --- LLM call ----------------------------------------------------------


async def _call_llm(facts: dict[str, Any], history: list[dict[str, str]], message: str) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("agent: no ANTHROPIC_API_KEY set, using deterministic answer")
        return None

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("agent: anthropic package not installed, using deterministic answer")
        return None

    # Facts are re-attached every turn: the underlying data moves, so an
    # earlier turn's numbers must never be what the model reasons from.
    turns = [
        *history,
        {
            "role": "user",
            "content": f"Facts:\n{json.dumps(facts, separators=(',', ':'))}\n\nQuestion: {message}",
        },
    ]

    try:
        client = AsyncAnthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
        response = await client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=turns,
        )
    except Exception as exc:  # noqa: BLE001 - any failure degrades to deterministic
        logger.warning("agent: LLM call failed (%s), using deterministic answer", exc)
        return None

    return "".join(block.text for block in response.content if block.type == "text").strip() or None


_PROACTIVE_POST_PROMPT = (
    "This is the opening line of the conversation — the manager just opened the chat and hasn't "
    "asked anything yet. Don't greet them or ask how you can help. Immediately say something "
    "specific and useful about the selected post's current numbers, as if you'd already been "
    "watching it."
)
_PROACTIVE_IDLE_PROMPT = (
    "This is the opening line of the conversation — the manager just opened the chat and hasn't "
    "asked anything yet. Don't greet them or ask how you can help. Immediately give a short "
    "'while you were away' briefing: what changed and what deserves attention first, if anything."
)


@router.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest, session: AsyncSession = Depends(get_db)) -> ChatResponse:
    facts = await build_facts(session, request.selected_post_id)
    history = _SESSIONS[request.session_id]

    # The proactive opening line reuses the same facts + guardrails as a
    # real question, it's just never something the manager actually typed —
    # so it gets its own instruction text and is never recorded as a user
    # turn below.
    prompt = (
        (_PROACTIVE_POST_PROMPT if facts.get("selected_post") else _PROACTIVE_IDLE_PROMPT)
        if request.proactive
        else request.message
    )

    reply = await _call_llm(facts, list(history), prompt)
    llm_available = reply is not None

    if reply is not None and not (
        _numbers_are_grounded(reply, facts) and _status_is_consistent(reply, facts)
    ):
        reply = None  # failed a guardrail: fall back rather than ship it

    if reply is None:
        reply = deterministic_answer(facts, "" if request.proactive else request.message)
        llm_available = False

    if not request.proactive:
        history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": reply})
    del history[:-MAX_HISTORY_MESSAGES]

    return ChatResponse(text=reply, facts_used=facts, llm_available=llm_available)


@router.delete("/agent/chat/{session_id}")
async def end_agent_session(session_id: str) -> dict[str, bool]:
    _SESSIONS.pop(session_id, None)
    return {"ended": True}
