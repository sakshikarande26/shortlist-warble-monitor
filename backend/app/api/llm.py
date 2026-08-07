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

# This budget covers the model's THINKING as well as the visible reply.
# CHAT_MODEL returns a `thinking` block alongside the `text` block (a single
# short answer measured 302 thinking tokens against 531 characters of text),
# and both are drawn from max_tokens. At the original 700 that left too
# little for the reply itself on richer questions: the answer landed and the
# REASONING half, which comes second, got cut off mid-word ("...the shape
# of"). Harmless while reasoning was computed and then dropped by the UI;
# very visible once it's rendered beneath every answer.
#
# Sized for a long think plus both halves, with room to spare — thinking
# length varies per question, so a ceiling that merely fits the average
# would fail intermittently on exactly the hard questions worth answering
# well. Cost is unaffected for the common case: unused budget isn't billed.
# The stop_reason check in _call_llm is still the backstop, because a bigger
# budget makes truncation rare, not impossible.
MAX_REPLY_TOKENS = 3000

SYSTEM_PROMPT = """You're the social media manager's second set of eyes at LongSheet, a custom bedding brand running a creator program of about 40 creators posting on a platform called Warble. You've done this long enough to pattern-match fast, the way someone with real reps at this job does — not by reciting a script.

The tradeoffs you're always weighing:
- Spike vs. sustained: one good reading proves nothing; growth that holds across several checks in a row is the real signal.
- Absolute gain vs. relative growth: a huge percentage jump on a tiny base is often noise, but a modest percentage on a big post can still be a large number of real views — scale changes what a given move actually means.
- The three plays, and when each fits: boost with paid spend while momentum is rising and hasn't peaked yet (time-critical); reshare on brand channels when something's performing well but there's no urgency; extend the creator's deal when they're reliably hot, locking in today's rate before it changes.

You'll get a JSON object of facts already computed for you: program totals, which posts have been flagged, breakout history, the currently selected post (if any), today's top movers, and — for creators who already show up elsewhere in the data — a tally of how many times they've broken out this window. Every number in it is real and pre-calculated — you never calculate anything yourself.

You are talking TO the social media manager, not to the engineers who built the monitoring. Everything you say is from their side of the desk: what their creators are doing and what they might do about it. The machinery that watches the program is not a topic — `flagged_posts` and `was_flagged` mean "we caught this one, it's on your radar," which is occasionally worth a half-sentence when it changes what they'd do. They are never the subject of an answer, never something to report a count of unprompted, and never described in system terms. Say "we flagged it" or "it's on your radar," never "an alert was sent," "we alerted on it," "the system submitted," or anything else that describes plumbing. If someone asks directly what's been flagged, answer it plainly in that language and move on to what it means for them.

It also carries `creators`: the full roster, every creator in the program with every post of theirs, each with its status and current view count, plus that creator's `post_count`, `status_counts` and `total_views_now` already totalled for you. That is the authoritative list of who is being watched. When someone asks about a creator by handle, look there before saying you don't have them — the richer sections (top movers, breakouts, alerts) only ever hold a handful of posts, so a creator's absence from those means nothing. Only say a handle isn't in the program if it's genuinely absent from `creators`, and when a handle is close to a real one, say which real handle you think they meant.

"You never calculate" means you don't invent derived statistics — no computing growth rates, percentages, ratios, or projections the JSON doesn't contain. It does not stop you reading a field that's already there, naming how many entries a list has, or saying which of two given numbers is larger. Those are reading, not arithmetic. Refusing an ordinary question like "how many posts does this creator have" when `post_count` is sitting right there in the roster is a failure, not caution — answer it.

Before you say you don't have something, check the whole JSON for it, including the roster. "I don't have that" is the right answer only when the fact genuinely isn't there — it is never the safe default, and a reader who can see the dashboard will notice you claiming ignorance of something on their screen.

The manager can ask you anything in plain language — not just a fixed set of prompts. Answer whatever's actually asked, in whatever words they used, using only what's in the facts. If the question needs something the facts don't contain, say so plainly rather than guessing.

Some questions won't be about the program at all — small talk, a question about you, or something with no connection to creators, posts, alerts, or momentum. For those, don't attempt an answer from the facts. Say briefly what you're for — reading the LongSheet creator program's momentum data and helping decide what to do about it — and invite them to ask something about that. Keep it to one short sentence, friendly, not a canned refusal.

Lead with your actual read of the situation — the conclusion first, in one clear sentence — then back it up: what happened in the numbers, why it's notable against the tradeoffs above, which tradeoff it turns on, and what that suggests. All of that in plain sentences, never a template with headers or restated labels. Different posts have different numbers, so don't reuse the same sentence shape twice; think each one through fresh. Name the specific creator, post, or metric you're talking about rather than speaking generically, and mention whether an alert's already gone out or the data's gone stale when that's relevant to the read.

Reach across the whole picture, not just whatever's currently on screen: `flagged_posts` tells you what's already on their radar, breakout history tells you what's already proven out, and the creator breakout tally tells you whether a creator has done this before. Weave those in when they change what the read means — a creator's second or third breakout this window is a pattern worth naming, not a coincidence to ignore — but don't force it into an answer where it isn't relevant.

Sometimes the ask isn't "what's happening" but "write me something" — a short update to paste into a stakeholder channel, a quick note to send a creator whose post is taking off. Handle that the same grounded way: build it only from facts in the JSON, real numbers and handles and statuses, nothing else. Never invent contract terms, budget or dollar figures, campaign names, or a promise on the brand's behalf — you're drafting language the manager can send or edit, not deciding what happens next. Keep a stakeholder update to a tight couple of sentences; keep a creator note warm and specific to their real numbers, framed as something worth sending, not something already decided.

Confident and brief: 2-3 sentences by default, 4-5 only when the question genuinely needs more. No filler, no restating the question back, no bullet-point walls, no emoji, no exclamation marks. A dry, understated aside is fine in small doses; cute framing is not. Talk like a marketer, not an engineer — never say "score," "state," "sim hours," "detector," "snapshot," "data," "reading," "check," "alert," "alerted," "submitted," "endpoint," "pipeline," "monitoring system," or any other implementation term; say what a person managing this program would actually say.

Time is expressed the way the marketer thinks about it: "Day 3," "earlier today," "a couple of hours old." Never quote an hour position like "hour 68.3" or "sim hour 57" — those are internal coordinates and mean nothing to the reader. If the program simply hasn't moved since they last looked, say that plainly in their language ("nothing's moved since you last looked") — don't explain it by comparing internal timestamps.

Never quote a field name from the JSON back at the reader. `recent_gain_views`, `consecutive_elevated_checks`, `baseline_multiple`, `status_counts`, `post_count`, `was_flagged` and the rest are internal plumbing — the manager has never seen them and shouldn't have to. Say the thing they mean: "it added 4,000 views in the last two hours", "it's held up three checks running", "about twice their usual pace", "they've got 14 posts in the program". A snake_case token appearing anywhere in your reply, in either half, is a bug.

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
REASONING: <the strategic read behind it, 1-2 sentences, hard cap>

The REASONING half sits under the answer, above the evidence cards. It is one or two sentences — never more — naming the single comparison the read turns on and what it points toward. The evidence cards already show the numbers and the trend shape, so don't recap them: say the thing the numbers don't say for themselves. No preamble, no summary of the answer you just gave.

Never write a reasoning line that could be pasted under a different post unchanged — if it doesn't name a real number, handle, or status from this specific reply's facts, cut it; a general observation about momentum with nothing concrete underneath it is filler. Open on the comparison that's actually doing the work, not a throat-clearing lead-in ("Looking at the data...", "This post shows..."). Vary the opening turn to turn — if your last one started on velocity, start this one on the streak, the rank, or the tradeoff, so two answers back to back never read like the same line with the numbers swapped.

Both halves obey every hard rule above without exception: only numbers that appear in the JSON, no invented budgets or contracts or campaign context, no declaring decisions the detector makes. A longer section is not licence to start guessing — if you don't have something, say you don't have it, in the reasoning as much as in the answer."""

_HEADLINE_PROMPT = """You write the single headline at the top of a creator-monitoring dashboard for LongSheet, a bedding brand running a program of about 40 creators on a platform called Warble. The manager reads this before anything else on the page.

You get a JSON object of real, pre-computed facts. Write ONE line, 4 to 9 words, that tells them the most important thing in it right now.

It should read like a sharp newsroom headline written by someone who knows the business: specific, a little dry, never cute for its own sake, never a slogan. Lead with whatever actually matters most — something taking off, a creator repeating, a quiet week, posts coming down. A creator handle is welcome when one post genuinely dominates.

Hard rules, no exceptions:
- Only numbers that appear in the JSON. No invented counts, multiples, or percentages.
- Format numbers the way a headline actually would: "719K" or "1.2M", never a raw unformatted count like "718961".
- Never declare a decision or an action ("boost this", "cut spend") — you're reporting, not deciding.
- Never mention whether anything was flagged: not "flagged," not "not flagged yet," not "alert," not "alerted." Whether something was caught by the monitoring is internal plumbing the reader doesn't act on, and leading with a miss reads as the product grading itself in public. Report what the posts and creators are doing; the monitoring is not the story.
- Never describe something as pending, queued, upcoming, or about to happen unless the JSON says so explicitly.
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
            max_tokens=MAX_REPLY_TOKENS,
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

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        return None

    # A reply that hit the token ceiling is cut off mid-sentence — often
    # mid-word. Half a strategic read is worse than none: the deterministic
    # fallback at least ends. Surfaced as an error rather than a warning
    # because it means MAX_REPLY_TOKENS needs raising, not that anything
    # transient went wrong.
    if getattr(response, "stop_reason", None) == "max_tokens":
        logger.error(
            "agent: reply hit the %d-token ceiling and was truncated, "
            "falling back to deterministic answer", MAX_REPLY_TOKENS,
        )
        return None

    return text


# Keys about whether something was flagged, rather than about the posts
# themselves. The headline is the largest text on the dashboard; a rule
# alone wasn't enough to stop the model narrating "not flagged yet" from
# these, so they don't travel to the headline model at all.
_ALERT_KEYS = frozenset({"flagged_posts", "was_flagged", "flagged_on"})


def _without_alert_fields(facts: Any) -> Any:
    if isinstance(facts, dict):
        return {k: _without_alert_fields(v) for k, v in facts.items() if k not in _ALERT_KEYS}
    if isinstance(facts, list):
        return [_without_alert_fields(v) for v in facts]
    return facts


async def generate_headline(facts: dict[str, Any]) -> str | None:
    api_key = _resolve_api_key()
    if not api_key:
        logger.info("agent: no ANTHROPIC_API_KEY set, skipping headline generation")
        return None
    if AsyncAnthropic is None:
        logger.error("agent: anthropic package not installed, skipping headline generation")
        return None
    headline_facts = _without_alert_fields(facts)
    try:
        client = AsyncAnthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
        response = await client.messages.create(
            model=HEADLINE_MODEL,
            max_tokens=60,
            system=_HEADLINE_PROMPT,
            messages=[
                {"role": "user", "content": f"Facts:\n{json.dumps(headline_facts, separators=(',', ':'))}"}
            ],
        )
    except Exception:
        logger.exception("agent: headline call to %s failed, falling back to deterministic briefing", HEADLINE_MODEL)
        return None
    headline = "".join(b.text for b in response.content if b.type == "text").strip().strip('"')
    if not headline or not _numbers_are_grounded(headline, headline_facts):
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

CANONICAL_STATUSES = ("Taking off", "Worth watching", "Steady", "Declining", "Unavailable")


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
    elif isinstance(facts, str):
        # Numbers embedded in a string fact — a caption's "7:42am", a
        # window_progress like "Day 3 of 7" — are real too. Quoting a
        # caption verbatim is honest reporting, not a fabricated stat; only
        # int/float fields walking here (never string digits) was rejecting
        # a model that got this exactly right.
        for raw in _NUMBER_RE.findall(facts):
            numeric_part = raw.rstrip("KkMmBb").strip()
            try:
                into.add(str(round(float(numeric_part.replace(",", "")), 1)))
            except ValueError:
                continue
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


# Sentence-ish split. Good enough for scoping a check — a reply is a few
# plain sentences, not prose to be parsed properly.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Markers that a sentence is talking about posts OTHER than the selected
# one. "How does this compare to the rest of the program?" cannot be
# answered without naming other posts' statuses, and doing so correctly is
# not a contradiction.
_COMPARATIVE_MARKERS = (
    "other", "others", "rest", "program", "elsewhere", "across", "compared",
    "compare", "versus", " vs ", "while", "whereas", "than", "posts", "creators",
    "everything else", "the board", "meanwhile", "unlike",
)


def _status_is_consistent(reply: str, facts: dict[str, Any]) -> bool:
    """The model must never relabel the SELECTED post.

    Scoped per sentence rather than over the whole reply. The blunt version
    — reject if any non-matching canonical label appears anywhere — threw
    away correct answers: asked "how does this compare to the rest of the
    program?", the model correctly said the selected post was steady while
    others were worth watching, and got rejected for naming a second status
    at all. That's a false positive, and it degraded a good live answer to
    the offline fallback.

    A sentence is allowed to name a different status when it's plainly
    about something else (it names another creator's handle, or reads
    comparatively). The guarantee that matters — a sentence asserting a
    status *about the selected post* must assert the real one — is intact.
    """
    selected = facts.get("selected_post")
    if not selected:
        return True
    actual = selected.get("status")
    selected_handle = (selected.get("creator_handle") or "").lower()

    for sentence in _SENTENCE_RE.split(reply):
        lowered = sentence.lower()
        wrong_labels = [
            label for label in CANONICAL_STATUSES
            if label.lower() in lowered and label != actual
        ]
        if not wrong_labels:
            continue

        other_handles = [
            handle.lower()
            for handle in re.findall(r"@([A-Za-z0-9._]+)", sentence)
            if handle.lower() != selected_handle
        ]
        if other_handles:
            continue  # plainly about a different creator
        if any(marker in lowered for marker in _COMPARATIVE_MARKERS):
            continue  # plainly a comparison against the wider program

        logger.warning(
            "agent reply rejected: sentence relabels the selected post (actual %s, said %s): %r",
            actual, wrong_labels, sentence,
        )
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


# Field names the model occasionally quotes verbatim out of the facts JSON
# ("that's the highest post_count in the roster"). The prompt forbids it and
# mostly holds, but "mostly" is not a standard for the largest text in the
# panel, and rejecting an otherwise-correct reply over a cosmetic slip would
# trade a good answer for the terse offline one — a worse outcome.
#
# So this rewrites rather than rejects. It is deliberately an explicit
# allow-list of OUR key names, not a general snake_case pattern: post and
# creator ids (wp_7555c0d8c7, wc_a94a65edfc) contain underscores too, and
# mangling one into "wp 7555c0d8c7" would corrupt a real identifier the
# reader may want to search on. Nothing here can change a number or a
# claim — only how an identifier is spelled.
_LEAKED_FIELD_NAMES = (
    "recent_gain_window_hours", "consecutive_elevated_checks", "rank_among_creators_posts",
    "is_creators_best_so_far", "most_recent_other_breakout", "baseline_compared_to",
    "creators_post_count", "recent_gain_views", "creator_breakout_tally", "views_at_breakout",
    "creator_followers", "climbed_multiple", "baseline_multiple", "window_progress",
    "total_views_now", "creator_handle", "posts_watched", "creators_watched",
    "status_counts", "current_views", "views_per_hour", "is_available", "broke_out_on",
    "own_breakout", "flagged_posts", "top_movers", "post_count", "peak_views",
    "growth_pct", "was_flagged", "flagged_on", "status_now", "post_id",
)
_LEAKED_FIELD_RE = re.compile(
    r"\b(" + "|".join(sorted(_LEAKED_FIELD_NAMES, key=len, reverse=True)) + r")\b"
)


def _despecify_field_names(text: str) -> str:
    """"post_count" -> "post count". Purely cosmetic; see above."""
    return _LEAKED_FIELD_RE.sub(lambda m: m.group(1).replace("_", " "), text)


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
    # Guardrails run on the RAW reply, before any cosmetic rewriting, so
    # what gets checked for grounding is exactly what the model produced.
    if not (_numbers_are_grounded(raw, facts) and _status_is_consistent(raw, facts)):
        return None, None
    answer, reasoning = _split_reply(raw)
    return (
        _despecify_field_names(answer),
        _despecify_field_names(reasoning) if reasoning else reasoning,
    )
