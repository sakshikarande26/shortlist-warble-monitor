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
    _samples_by_post,
    get_db,
)
from app.db.models import Alert, Creator, Post
from app.detector.momentum import _dedupe_samples
from app.detector.states import run_state_machine

logger = logging.getLogger(__name__)

router = APIRouter()

MODEL = "claude-haiku-4-5"
LLM_TIMEOUT_SECONDS = 10.0
MAX_HISTORY_MESSAGES = 24  # ~12 turns
MAX_BREAKOUTS = 10
MAX_ALERTS = 10
MAX_MOVERS = 5
MONITORING_WINDOW_DAYS = 7

CANONICAL_STATUSES = (_TAKING_OFF, _WORTH_WATCHING, _STEADY, _UNAVAILABLE)

SYSTEM_PROMPT = """You are the monitoring analyst inside a tool used by the social media manager at LongSheet, a custom bedding brand. LongSheet runs a creator program: about 40 creators post LongSheet content on a social platform called Warble. The tool watches every post's view counts over time and flags posts whose growth becomes unusually fast and sustained, a "breakout." When a post breaks out, the moment to act is short: boost it, reshare it, or call the creator and extend the deal.

You will receive a JSON object of already-computed facts: program totals, alert history, breakout history, the currently selected post if any, and the current top movers. Everything numeric has already been calculated for you.

Your job is to help the manager think. You turn monitoring facts into meaning.

Hard rules:
- Use ONLY facts present in the input JSON. Never state a number, percentage, multiple, date, or comparison that is not there. If you want to cite something you weren't given, say you don't have it.
- Do not restate numbers the interface already shows. Interpret them. Say what the movement implies, not what it measures.
- You never decide. You do not declare something "is a breakout" or that it "should be boosted" - the system's deterministic detector decides status, not you. Frame everything as a consideration: "worth considering," "you may want to," "this looks like the kind of thing that..."
- Never invent context: no contracts, budgets, usage rights, campaign goals, audience demographics, revenue, or competitor data. You do not know these.
- Never contradict the status field for any post.
- Never imply causation from engagement metrics alone.
- If the facts are insufficient, say plainly what's missing and what would settle it, rather than speculating.

Answer in 2-4 short sentences unless the question genuinely needs more. Calm, direct, plain English. No emoji, no hype, no exclamation marks, no bullet-point walls.

You have conversation memory within this session. Refer back naturally to posts already discussed."""


# --- Session memory (in-process, per session_id) -----------------------
# Deliberately not persisted: a chat is a working conversation, not a
# record, and the facts are re-computed fresh every turn anyway.
_SESSIONS: dict[str, list[dict[str, str]]] = defaultdict(list)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    selected_post_id: str | None = None


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

    def pace(post: Post) -> float:
        ev = computations[post.id].evidence
        if ev is None or ev.creator_pace_ratio is None:
            return float("-inf")
        return ev.creator_pace_ratio

    movers = sorted(
        (p for p in posts if p.status != "gone" and computations[p.id].status_label != _STEADY),
        key=pace,
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
        }

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
    }


# --- Guardrails --------------------------------------------------------

_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


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
        into.add(f"{float(facts):.1f}")
        into.add(str(int(facts)) if float(facts).is_integer() else f"{float(facts):.1f}")
        into.add(f"{int(facts):,}" if float(facts).is_integer() else f"{facts:,.1f}")
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
        try:
            value = round(float(raw.replace(",", "")), 1)
        except ValueError:
            return False
        if value in allowed_floats:
            continue
        # A rounded restatement of a real fact is fine; a novel number is not.
        if any(abs(value - candidate) < 0.05 for candidate in allowed_floats):
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


def deterministic_answer(facts: dict[str, Any]) -> str:
    """Used whenever the model is unavailable or its reply fails a
    guardrail. Says only what the facts say, in the same calm register."""
    selected = facts.get("selected_post")
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


@router.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest, session: AsyncSession = Depends(get_db)) -> ChatResponse:
    facts = await build_facts(session, request.selected_post_id)
    history = _SESSIONS[request.session_id]

    reply = await _call_llm(facts, list(history), request.message)
    llm_available = reply is not None

    if reply is not None and not (
        _numbers_are_grounded(reply, facts) and _status_is_consistent(reply, facts)
    ):
        reply = None  # failed a guardrail: fall back rather than ship it

    if reply is None:
        reply = deterministic_answer(facts)
        llm_available = False

    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": reply})
    del history[:-MAX_HISTORY_MESSAGES]

    return ChatResponse(text=reply, facts_used=facts, llm_available=llm_available)


@router.delete("/agent/chat/{session_id}")
async def end_agent_session(session_id: str) -> dict[str, bool]:
    _SESSIONS.pop(session_id, None)
    return {"ended": True}
