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

import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import llm
from app.api.routes import (
    _DECLINING,
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

MAX_HISTORY_MESSAGES = 24  # ~12 turns
MAX_BREAKOUTS = 10
MAX_ALERTS = 10
MAX_MOVERS = 5
MAX_CREATOR_TALLY = 5
MONITORING_WINDOW_DAYS = 7

CANONICAL_STATUSES = (_TAKING_OFF, _WORTH_WATCHING, _STEADY, _DECLINING, _UNAVAILABLE)


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
    # The strategic read behind `text`, shown beside the evidence. None
    # when the model didn't produce one (or wasn't available at all) —
    # the panel simply omits it rather than inventing filler.
    reasoning: str | None
    facts_used: dict[str, Any]
    llm_available: bool


def _window_progress(sim_hours: float | None) -> str | None:
    if sim_hours is None:
        return None
    return f"{_day_label(sim_hours)} of {MONITORING_WINDOW_DAYS}"


def _day_label(sim_hours: float | None) -> str | None:
    """"Day 3" — how a marketer refers to a moment in the tracking window.

    Raw sim hours are an internal coordinate: "sim hour 57.4" means nothing
    to someone reading the panel, and the model will happily quote any
    number it's handed. So the payload carries day labels and durations,
    and never an absolute sim-hour position to echo back.
    """
    if sim_hours is None:
        return None
    return f"Day {min(int(sim_hours // 24) + 1, MONITORING_WINDOW_DAYS)}"


def _evidence_facts(evidence: Any) -> dict[str, Any]:
    """Only the fields the agent is allowed to reason about. Raw internal
    scores stay out — they aren't marketer-meaningful and inviting the
    model to narrate them would violate the language rules."""
    if evidence is None:
        return {}
    return {
        "recent_gain_views": evidence.absolute_gain,
        "recent_gain_window_hours": evidence.window_hours,
        "growth_pct": (
            round(evidence.relative_growth_pct, 1) if evidence.relative_growth_pct is not None else None
        ),
        "views_per_hour": round(evidence.velocity, 1),
        "baseline_multiple": (
            round(evidence.creator_pace_ratio, 1) if evidence.creator_pace_ratio is not None else None
        ),
        "baseline_compared_to": evidence.creator_pace_basis,
        "consecutive_elevated_checks": evidence.consecutive_qualifying_checks,
    }


# The shape behind the numbers — recent view readings, for the sparkline on
# an evidence card. Strictly UI-only: _model_facts() strips these before the
# payload reaches the model, so a dozen raw view counts per post never widen
# what the grounding guardrail accepts, and never burn tokens on a list the
# model has no use for anyway.
TREND_POINTS = 12


def _trend(sample_points: list[SamplePoint]) -> list[int]:
    return [p.views for p in _dedupe_samples(sample_points)[-TREND_POINTS:]]


def _model_facts(facts: Any) -> Any:
    """The same facts with every UI-only `trend` array removed — what the
    model actually gets, and what the guardrail grounds its reply against."""
    if isinstance(facts, dict):
        return {k: _model_facts(v) for k, v in facts.items() if k != "trend"}
    if isinstance(facts, list):
        return [_model_facts(v) for v in facts]
    return facts


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

    # Named for what it means to the reader, not for the mechanism behind
    # it. The manager doesn't think "an alert was POSTed to an endpoint" —
    # they think "we caught this one, it's on the radar." The model echoes
    # the vocabulary it's handed, so handing it `alerts`/`submitted` was
    # itself the reason replies came back talking like a system log.
    flagged_posts = []
    for row in alert_rows[:MAX_ALERTS]:
        post = posts_by_id.get(row.post_id)
        creator = creators.get(post.creator_id) if post else None
        flagged_posts.append(
            {
                "post_id": row.post_id,
                "creator_handle": creator.handle if creator else "unknown",
                "caption": post.caption if post else None,
                "flagged_on": _day_label(row.decided_sim_hours),
                "was_flagged": row.submitted,
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
                "broke_out_on": _day_label(first.sim_hours),
                # Sort key only — dropped from the payload below so the
                # model never sees an absolute hour to quote.
                "_sort_sim_hours": first.sim_hours,
                "views_at_breakout": at_breakout,
                "peak_views": peak,
                "climbed_multiple": round(peak / at_breakout, 1) if at_breakout > 0 else None,
                "was_flagged": post.id in submitted_ids,
                "status_now": comp.status_label,
                "trend": [p.views for p in points[-TREND_POINTS:]],
            }
        )
    breakouts.sort(key=lambda b: b["_sort_sim_hours"], reverse=True)
    breakouts = [{k: v for k, v in b.items() if k != "_sort_sim_hours"} for b in breakouts[:MAX_BREAKOUTS]]

    # "Movers" means outpacing the creator's own norm — growth, not decline —
    # so a declining post is excluded here same as a steady one; it has no
    # creator_pace_ratio anyway (that's only computed on rankable positive
    # movement) and would just sort to the bottom on _pace_sort_key's -inf.
    movers = sorted(
        (p for p in posts if p.status != "gone" and computations[p.id].status_label not in (_STEADY, _DECLINING)),
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
                "trend": _trend(comp.sample_points),
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
            "was_flagged": post.id in submitted_ids,
            "is_available": post.status != "gone",
            "trend": _trend(comp.sample_points),
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

    relevant_handles = {a["creator_handle"] for a in flagged_posts} | {m["creator_handle"] for m in top_movers}
    if selected:
        relevant_handles.add(selected["creator_handle"])
    creator_breakout_tally = _creator_breakout_tally(breakouts, relevant_handles)

    # Every creator and every post, in compact form. Without this the model
    # only ever saw the handful of posts that made it into top movers, alerts
    # or breakouts — so a question about any other creator got a truthful but
    # useless "I don't have anyone by that handle," about someone the program
    # is very much watching. It's also what lets the panel cite a reference
    # card for a creator outside those slices.
    posts_by_creator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        comp = computations[post.id]
        latest = comp.latest
        posts_by_creator[post.creator_id].append(
            {
                "post_id": post.id,
                "caption": post.caption,
                "status": comp.status_label,
                "current_views": latest.views if latest else None,
                "is_available": post.status != "gone",
                "trend": _trend(comp.sample_points),
            }
        )

    roster = []
    for creator in sorted(creators.values(), key=lambda c: c.handle):
        own = sorted(
            posts_by_creator.get(creator.id, []),
            key=lambda p: p["current_views"] or 0,
            reverse=True,
        )
        status_tally: dict[str, int] = defaultdict(int)
        for entry in own:
            status_tally[entry["status"]] += 1
        roster.append(
            {
                "creator_handle": creator.handle,
                "creator_followers": creator.followers,
                # Pre-counted: the model is told not to do arithmetic, so a
                # question as ordinary as "how many posts do they have" has
                # to be answerable by reading a field, not by counting a list.
                "post_count": len(own),
                "status_counts": dict(status_tally),
                "total_views_now": sum(p["current_views"] or 0 for p in own),
                "posts": own,
            }
        )

    return {
        "creators": roster,
        "program": {
            "posts_watched": len(posts),
            "creators_watched": len(creators),
            "status_counts": status_counts,
            "window_progress": _window_progress(current_sim),
        },
        "flagged_posts": flagged_posts,
        "breakouts": breakouts,
        "selected_post": selected,
        "top_movers": top_movers,
        "creator_breakout_tally": creator_breakout_tally,
    }


# --- Offline fallback ---------------------------------------------------
# Used only when the model is genuinely unavailable (no key, package
# missing, network/API failure) or its reply fails a guardrail. One honest,
# fully-grounded summary — never a matrix of pretend-specific canned
# answers pretending to address whatever was actually asked.


def offline_answer(facts: dict[str, Any]) -> str:
    selected = facts.get("selected_post")
    if selected:
        parts = [f"@{selected['creator_handle']}'s post is currently {selected['status'].lower()}."]
        gain = selected.get("recent_gain_views")
        window = selected.get("recent_gain_window_hours")
        if gain is not None and window:
            verb = "added" if gain >= 0 else "lost"
            parts.append(f"It {verb} {abs(gain):,} views in the last {window:g}h.")
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
            "This one is already on your radar — we flagged it."
            if selected.get("was_flagged")
            else "It hasn't been flagged yet."
        )
        return " ".join(parts)

    program = facts["program"]
    counts = program["status_counts"]
    taking_off = counts.get(_TAKING_OFF, 0)
    watching = counts.get(_WORTH_WATCHING, 0)
    breakouts = len(facts["breakouts"])
    flagged = sum(1 for a in facts["flagged_posts"] if a["was_flagged"])
    breakouts_phrase = f"{breakouts} breakout{'' if breakouts == 1 else 's'}"
    flagged_phrase = f"flagged {flagged} of them"

    if taking_off == 0 and watching == 0:
        return (
            "Nothing is taking off or worth watching at the moment — it's a quiet stretch. "
            f"Across the window so far we've seen {breakouts_phrase} and {flagged_phrase}."
        )

    bits = []
    if taking_off:
        bits.append(f"{taking_off} taking off")
    if watching:
        bits.append(f"{watching} worth watching")
    return (
        f"There's {' and '.join(bits)} right now. "
        f"Across the window so far we've seen {breakouts_phrase} and {flagged_phrase}."
    )


def deterministic_reasoning(facts: dict[str, Any]) -> str:
    """The offline counterpart to the model's REASONING half: the same
    strategic framing, assembled from real facts. Plainer than the model's
    version by design — an offline panel should read as deliberately terse
    rather than as a failed attempt at prose."""
    selected = facts.get("selected_post")
    if selected:
        parts: list[str] = []
        multiple = selected.get("baseline_multiple")
        if multiple is not None:
            basis = (
                "this creator's usual pace"
                if selected.get("baseline_compared_to") == "creator"
                else "its own earlier pace"
            )
            parts.append(
                f"@{selected['creator_handle']}'s post is pacing about {multiple}x {basis}, which is the "
                f"comparison that matters more than raw reach here."
            )
        else:
            parts.append(
                f"@{selected['creator_handle']}'s post doesn't have enough history yet to compare its pace "
                f"against anything, so there's no read to give on momentum."
            )

        streak = selected.get("consecutive_elevated_checks") or 0
        if streak >= 3:
            parts.append(
                f"It's held that across {streak} checks in a row — sustained rather than a single spike, "
                f"which is the version worth putting spend behind."
            )
        elif streak == 2:
            parts.append("Two checks in a row have qualified; one more would settle whether this holds.")
        else:
            parts.append("The streak is too short to separate real momentum from one good reading.")

        if selected.get("was_flagged"):
            parts.append("It's already been flagged, so the window to amplify is now rather than later.")
        else:
            parts.append("It hasn't been flagged yet, so there's still room to decide before it's obvious.")
        return " ".join(parts)

    movers = facts["top_movers"]
    breakouts = facts["breakouts"]
    flagged = sum(1 for a in facts["flagged_posts"] if a["was_flagged"])
    if not movers:
        return (
            f"Nothing is outpacing its creator's own norm right now, across "
            f"{facts['program']['posts_watched']} tracked posts. That's a quiet program, not a broken one — "
            f"{len(breakouts)} posts have broken out over the window and {flagged} were flagged."
        )

    top = movers[0]
    lead = f"@{top['creator_handle']} is the clearest mover, currently {top['status'].lower()}"
    multiple = top.get("baseline_multiple")
    if multiple is not None:
        lead += f" at about {multiple}x its creator's usual pace"
    return (
        f"{lead}. {len(movers)} posts in total are running above their own creator's norm, which is the "
        f"comparison to trust when creator sizes differ this much. Across the window {len(breakouts)} posts "
        f"have broken out and {flagged} were flagged — worth weighing before committing spend anywhere."
    )


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

    reply, reasoning = await llm.generate_reply(_model_facts(facts), list(history), prompt)
    llm_available = reply is not None

    if reply is None:
        reply = offline_answer(facts)
        reasoning = deterministic_reasoning(facts)

    if not request.proactive:
        history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": reply})
    del history[:-MAX_HISTORY_MESSAGES]

    return ChatResponse(
        text=reply, reasoning=reasoning, facts_used=facts, llm_available=llm_available
    )


class HeadlineResponse(BaseModel):
    headline: str | None
    llm_available: bool


@router.get("/agent/headline", response_model=HeadlineResponse)
async def get_headline(session: AsyncSession = Depends(get_db)) -> HeadlineResponse:
    """The dashboard's top line, written fresh from current facts. Its own
    endpoint rather than part of /home so the page never waits on a model
    call to render — the deterministic briefing shows immediately and this
    replaces it if and when it arrives."""
    facts = await build_facts(session, None)
    headline = await llm.generate_headline(_model_facts(facts))
    return HeadlineResponse(headline=headline, llm_available=headline is not None)


@router.delete("/agent/chat/{session_id}")
async def end_agent_session(session_id: str) -> dict[str, bool]:
    _SESSIONS.pop(session_id, None)
    return {"ended": True}
