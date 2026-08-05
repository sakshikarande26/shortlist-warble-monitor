"""Everything specific to talking to the Anthropic model: prompts, the
actual API call, and the guardrails that check its output before it's
trusted. agent.py owns facts and routes; this module owns the model.
"""

import json
import logging
import os
import re
from typing import Any

from app.config import settings

# Imported at module load (server startup), not lazily inside a request
# handler: the SDK's first import can be slow on a constrained filesystem,
# and paying that cost once at startup is fine — paying it on a live
# user's first chat message looks exactly like the endpoint hanging or
# erroring. Graceful fallback preserved: the app still boots (and degrades
# to deterministic answers) if the package genuinely isn't installed.
try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-5"
# The headline is a single short line generated on every dashboard load —
# cheaper/faster model is enough for it and keeps that path non-blocking.
HEADLINE_MODEL = "claude-haiku-4-5-20251001"
LLM_TIMEOUT_SECONDS = 45.0

SYSTEM_PROMPT = """You're the social media manager's second set of eyes at LongSheet, a custom bedding brand running a creator program of about 40 creators posting on a platform called Warble. You've done this long enough to pattern-match fast, the way someone with real reps at this job does — not by reciting a script.

The tradeoffs you're always weighing:
- Spike vs. sustained: one good reading proves nothing; growth that holds across several checks in a row is the real signal.
- Absolute gain vs. relative growth: a huge percentage jump on a tiny base is often noise, but a modest percentage on a big post can still be a large number of real views — scale changes what a given move actually means.
- The three plays, and when each fits: boost with paid spend while momentum is rising and hasn't peaked yet (time-critical); reshare on brand channels when something's performing well but there's no urgency; extend the creator's deal when they're reliably hot, locking in today's rate before it changes.

You'll get a JSON object of facts already computed for you: program totals, alert history, breakout history, the currently selected post (if any), today's top movers, and — for creators who already show up elsewhere in the data — a tally of how many times they've broken out this window. Every number in it is real and pre-calculated — you never calculate anything yourself.

The manager can ask you anything in plain language — not just a fixed set of prompts. Answer whatever's actually asked, in whatever words they used, using only what's in the facts. If the question needs something the facts don't contain, say so plainly rather than guessing.

Some questions won't be about the program at all — small talk, a question about you, or something with no connection to creators, posts, alerts, or momentum. For those, don't attempt an answer from the facts. Say briefly what you're for — reading the LongSheet creator program's momentum data and helping decide what to do about it — and invite them to ask something about that. Keep it to one short sentence, friendly, not a canned refusal.

Lead with your actual read of the situation — the conclusion first, in one clear sentence — then back it up: what happened in the numbers, why it's notable against the tradeoffs above, which tradeoff it turns on, and what that suggests. All of that in plain sentences, never a template with headers or restated labels. Different posts have different numbers, so don't reuse the same sentence shape twice; think each one through fresh. Name the specific creator, post, or metric you're talking about rather than speaking generically, and mention whether an alert's already gone out or the data's gone stale when that's relevant to the read.

Reach across the whole picture, not just whatever's currently on screen: alert history tells you what's already been flagged, breakout history tells you what's already proven out, and the creator breakout tally tells you whether a creator has done this before. Weave those in when they change what the read means — a creator's second or third breakout this window is a pattern worth naming, not a coincidence to ignore — but don't force it into an answer where it isn't relevant.

Sometimes the ask isn't "what's happening" but "write me something" — a short update to paste into a stakeholder channel, a quick note to send a creator whose post is taking off. Handle that the same grounded way: build it only from facts in the JSON, real numbers and handles and statuses, nothing else. Never invent contract terms, budget or dollar figures, campaign names, or a promise on the brand's behalf — you're drafting language the manager can send or edit, not deciding what happens next. Keep a stakeholder update to a tight couple of sentences; keep a creator note warm and specific to their real numbers, framed as something worth sending, not something already decided.

Confident and brief: 2-3 sentences by default, 4-5 only when the question genuinely needs more. No filler, no restating the question back, no bullet-point walls, no emoji, no exclamation marks. A dry, understated aside is fine in small doses; cute framing is not. Talk like a marketer, not an engineer — never say "score," "state," "sim hours," "detector," or any other implementation term; say what a person managing this program would actually say.

Hard rules:
- Use ONLY facts present in the input JSON. Never state a number, percentage, multiple, date, or comparison that is not there. If you want to cite something you weren't given, say you don't have it.
- Do not restate numbers the interface already shows unless the number itself is doing real work in your explanation. Interpret them. Say what the movement implies, not what it measures.
- You never decide. You do not declare something "is a breakout" or that it "should be boosted" - the system's deterministic detector decides status, not you. Frame everything as a consideration: "worth considering," "you may want to," "this looks like the kind of thing that..."
- Never invent context: no contracts, budgets, dollar figures, revenue, conversions, sentiment, business impact, usage rights, campaign goals, audience demographics, or competitor data. You do not know any of these — if asked, say so plainly rather than guessing.
- Never contradict the status field for any post.
- Never imply causation from engagement metrics alone.
- If the facts are insufficient, say plainly what's missing and what would settle it, rather than speculating.
- When asked to explain something "for leadership," "for Slack," or similar, compress to 1-2 plain sentences — same facts, no jargon, ready to paste into an update. Drop hedging language in that mode; state the read plainly.

You have conversation memory within this session. Refer back naturally to posts already discussed instead of re-introducing them.

Every reply you write has exactly two parts, in this format, with these literal labels:

ANSWER: <the reply itself, following everything above — brief, plain, 2-3 sentences>
REASONING: <the strategic read behind it, 3-5 sentences>

The REASONING half is your working-out, shown in the manager's side panel next to the evidence. It's where you get room to think out loud: walk the trajectory the numbers actually trace, name which tradeoff this one turns on and why you weighed it the way you did, and land on the play it points toward and the window for it. Talk like a strategist who's run creator programs before — reach, momentum, pacing, amplification, paid support, whitelisting, organic lift, creative, the deal — and let some dry wit through, the kind that comes from having seen this pattern before, never a joke that costs the reader clarity. It's a short story with a point, not a bulleted recap and not an essay.

Never write a reasoning paragraph that could be pasted under a different post unchanged — if a sentence doesn't name a real number, handle, or status from this specific reply's facts, cut it; a general observation about momentum or pacing with nothing concrete underneath it is filler, not reasoning. Open each one on the number or comparison that's actually doing the work here, not a throat-clearing lead-in ("Looking at the data...", "This post shows..."). Across a session, vary your opening move and sentence rhythm turn to turn — if your last reasoning started by naming the velocity, start this one on the streak, the rank, or the tradeoff instead, so two answers back to back never read like the same paragraph with the numbers swapped out.

Both halves obey every hard rule above without exception: only numbers that appear in the JSON, no invented budgets or contracts or campaign context, no declaring decisions the detector makes. A longer section is not licence to start guessing — if you don't have something, say you don't have it, in the reasoning as much as in the answer."""

_HEADLINE_PROMPT = """You write the single headline at the top of a creator-monitoring dashboard for LongSheet, a bedding brand running a program of about 40 creators on a platform called Warble. The manager reads this before anything else on the page.

You get a JSON object of real, pre-computed facts. Write ONE line, 4 to 9 words, that tells them the most important thing in it right now.

It should read like a sharp newsroom headline written by someone who knows the business: specific, a little dry, never cute for its own sake, never a slogan. Lead with whatever actually matters most — something taking off, a creator repeating, a quiet week, posts coming down. A creator handle is welcome when one post genuinely dominates.

Hard rules, no exceptions:
- Only numbers that appear in the JSON. No invented counts, multiples, or percentages.
- Format numbers the way a headline actually would: "719K" or "1.2M", never a raw unformatted count like "718961".
- Never declare a decision or an action ("boost this", "cut spend") — you're reporting, not deciding.
- Never describe something as pending, queued, upcoming, or about to happen unless the JSON says so explicitly. A post that broke out without ever being alerted is a closed historical fact ("never alerted" / "no alert sent"), not something in progress — do not say "pending" or imply anything is still coming.
- No emoji, no exclamation marks, no trailing period, no quote marks around the line.
- Output the headline alone. No labels, no preamble, nothing else."""


def _resolve_api_key() -> str | None:
    # Env var first so a shell/CI override still wins, then settings —
    # which is the only place a key living in .env actually lands, since
    # pydantic-settings never exports into os.environ.
    return os.environ.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key


def is_configured() -> bool:
    return bool(_resolve_api_key()) and AsyncAnthropic is not None


async def _call_llm(facts: dict[str, Any], history: list[dict[str, str]], message: str) -> str | None:
    api_key = _resolve_api_key()
    if not api_key:
        logger.info("agent: no ANTHROPIC_API_KEY set, using deterministic answer")
        return None
    if AsyncAnthropic is None:
        logger.error("agent: anthropic package not installed, using deterministic answer")
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
            model=CHAT_MODEL,
            max_tokens=700,  # room for the reasoning half as well as the answer
            # Cached: this prompt is large, static, and sent on every chat
            # turn — caching it cuts repeat-call cost and latency (Anthropic
            # prompt caching), with no change in behavior.
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=turns,
        )
    except Exception:
        # Logged loudly (not a warning) — a failed live call degrading to the
        # offline fallback should be visible as a real incident, not masked
        # as routine "fallback mode".
        logger.exception("agent: LLM call to %s failed, falling back to deterministic answer", CHAT_MODEL)
        return None

    return "".join(block.text for block in response.content if block.type == "text").strip() or None


async def generate_headline(facts: dict[str, Any]) -> str | None:
    api_key = _resolve_api_key()
    if not api_key:
        logger.info("agent: no ANTHROPIC_API_KEY set, skipping headline generation")
        return None
    if AsyncAnthropic is None:
        logger.error("agent: anthropic package not installed, skipping headline generation")
        return None
    try:
        client = AsyncAnthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
        response = await client.messages.create(
            model=HEADLINE_MODEL,
            max_tokens=60,
            system=_HEADLINE_PROMPT,
            messages=[{"role": "user", "content": f"Facts:\n{json.dumps(facts, separators=(',', ':'))}"}],
        )
    except Exception:
        logger.exception("agent: headline call to %s failed, falling back to deterministic briefing", HEADLINE_MODEL)
        return None
    headline = "".join(b.text for b in response.content if b.type == "text").strip().strip('"')
    if not headline or not _numbers_are_grounded(headline, facts):
        return None
    return headline


# --- Guardrails --------------------------------------------------------

# Trailing K/M/B captured so "40K" is recognized as shorthand for 40000
# rather than parsed as the bare number 40 and rejected as invented — a
# writer abbreviating a real fact isn't the same as inventing a smaller one.
# The spelled-out form ("719 thousand") gets the same treatment: nothing in
# the system prompt forces K/M/B shorthand outside the headline, so the chat
# model routinely writes scale out in prose, and without this a perfectly
# grounded 719,432 becomes a bare, unrecognized "719" that fails the
# tolerance check below and gets rejected as if it were invented.
# Leading (?<![A-Za-z0-9_]) excludes digits embedded in an alphanumeric
# token — e.g. the "7555" inside post id "wp_7555c0d8c7" — which are an
# identifier, not a numeric claim, and were being flagged as ungrounded.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])\d+(?:,\d{3})*(?:\.\d+)?(?:[KkMmBb]\b|\s+(?:thousand|million|billion)\b)?",
    re.IGNORECASE,
)
_SCALE_SUFFIXES = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
_SCALE_WORDS = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_SCALE_WORD_RE = re.compile(r"\s+(thousand|million|billion)$", re.IGNORECASE)

CANONICAL_STATUSES = ("Taking off", "Worth watching", "Steady", "Unavailable")


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


# Small counting numbers ("the next 2-3 days", "day 3", "a second look")
# are normal English, not statistics — and several real facts (like
# window_progress: "Day 3 of 7") are stored as strings, so their digits
# never enter `allowed`. Exempting anything this small from the grounding
# check removes that false-positive source while leaving the guardrail's
# actual job — blocking a fabricated, precise-looking metric — untouched:
# a real hallucinated stat (a view count, a percentage, a multiple) is
# essentially never this small.
_SMALL_NUMBER_EXEMPT_MAX = 20


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
        word_match = _SCALE_WORD_RE.search(raw)
        if word_match:
            multiplier = _SCALE_WORDS[word_match.group(1).lower()]
            numeric_part = raw[: word_match.start()]
            has_scale = True
        elif raw and raw[-1].upper() in _SCALE_SUFFIXES:
            multiplier = _SCALE_SUFFIXES[raw[-1].upper()]
            numeric_part = raw[:-1]
            has_scale = True
        else:
            multiplier = 1
            numeric_part = raw
            has_scale = False
        try:
            value = float(numeric_part.replace(",", "")) * multiplier
        except ValueError:
            return False
        value = round(value, 1)
        if not has_scale and 0 <= value <= _SMALL_NUMBER_EXEMPT_MAX:
            continue
        if value in allowed_floats:
            continue
        # A rounded restatement of a real fact is fine ("993" for 993.1,
        # "718K" for 718961, "719 thousand" for 719432); a genuinely
        # invented number is not. Tolerance is relative (2% of the real
        # value, floor 0.5) rather than a fixed amount, so it scales
        # sensibly whether the underlying fact is a small count or a
        # six-figure view total — a fabricated stat is essentially always
        # far outside this, a natural-language rounding essentially always
        # inside it.
        if any(abs(value - candidate) <= max(0.5, abs(candidate) * 0.02) for candidate in allowed_floats):
            continue
        logger.warning(
            "agent reply rejected: ungrounded number %s (parsed=%s) in reply=%r", raw, value, reply
        )
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


# The model is asked for "ANSWER: ... REASONING: ..." — tolerant of the
# labels being bolded, lower-cased, or missing entirely, because a reply
# that ignores the format is still a usable answer and shouldn't be thrown
# away over punctuation.
_ANSWER_LABEL_RE = re.compile(r"^\s*\**\s*answer\s*\**\s*:\s*", re.IGNORECASE)
_REASONING_LABEL_RE = re.compile(r"\n\s*\**\s*reasoning\s*\**\s*:\s*", re.IGNORECASE)


def _split_reply(raw: str) -> tuple[str, str | None]:
    """Split the model's two-part output into (answer, reasoning). Falls
    back to treating the whole thing as the answer when the model didn't
    use the format — never drops content on the floor."""
    body = _ANSWER_LABEL_RE.sub("", raw, count=1)
    match = _REASONING_LABEL_RE.search(body)
    if match is None:
        return body.strip(), None
    answer = body[: match.start()].strip()
    reasoning = body[match.end() :].strip()
    return (answer or body.strip()), (reasoning or None)


async def generate_reply(
    facts: dict[str, Any], history: list[dict[str, str]], message: str
) -> tuple[str | None, str | None]:
    """The one entry point agent.py needs: ask the model, apply both
    guardrails, and hand back (answer, reasoning) — or (None, None) if the
    model is unavailable or its reply didn't pass. Grounding runs over the
    whole raw reply (both halves) before splitting, since a fabricated
    number is no more acceptable in the reasoning panel than in the chat."""
    raw = await _call_llm(facts, history, message)
    if raw is None:
        return None, None
    if not (_numbers_are_grounded(raw, facts) and _status_is_consistent(raw, facts)):
        return None, None
    return _split_reply(raw)
