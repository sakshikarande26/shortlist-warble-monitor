# Shortlist Warble Monitor

A breakout-detection and alerting product for **LongSheet**, a custom bedding
brand running a ~40-creator program on the Warble social platform. It polls
Warble's API under a strict budget, decides — deterministically — which
posts are "breaking out" (sustained, unusual growth), alerts on them once,
and gives LongSheet's social media manager a dashboard plus an AI teammate to
ask about what's happening and why.

This was built as a take-home for Shortlist's AI Product Engineering role.
See [`CLAUDE.md`](CLAUDE.md) for the original brief and hard constraints, and
[`docs/`](docs/) for the product framing (`PRODUCT.md`), the engineering
decision log (`DECISIONS.md`), and the frontend's copy rules (`FRONTEND.md`).

## Architecture

```
Warble API
    │  GET /me, /creators, /creators/:id/posts (cached),
    │  /posts/batch (live), POST /alerts
    ▼
Collector (backend/app/collector/)
    │  three independent async loops: heartbeat (clock), discovery
    │  (cheap/wide, ~6h), live sampling (dense, ~15min, batches of 10)
    │  writes every reading append-only to Postgres/SQLite
    ▼
Detector (backend/app/detector/)
    │  pure functions: samples in, momentum score + state out
    │  (momentum.py → states.py → evaluate.py)
    ▼
Alerter (backend/app/alerts/)
    │  fires POST /alerts once per post at BREAKOUT, budget-aware,
    │  two dedupe layers, queues rather than drops under 429/budget
    ▼
API (backend/app/api/routes.py)
    │  read-only FastAPI routes for the dashboard — never calls Warble,
    │  never touches collector/detector/alert state
    ▼
Frontend (frontend/, React + Vite + TS)      Agent (backend/app/api/agent.py)
    dashboard: triage, creators, post detail,   grounded chat: Python computes
    breakout log                                every fact, the LLM only
                                                 narrates what they mean
```

The collector, detector, and alerter run as one always-on background process
(`backend/app/collector/loop.py`). The FastAPI app (`backend/app/main.py`)
serves the read-only dashboard API and (in production) the built frontend
from the same origin, so there's a single deployable service.

## Running locally

### Backend

```bash
cd backend
uv sync                      # or: pip install -e .
cp .env.example .env         # set WARBLE_API_KEY, DATABASE_URL
uv run alembic upgrade head  # creates warble.db (SQLite) or migrates Postgres
uv run uvicorn app.main:app --reload --port 8001
```

`DATABASE_URL` defaults to a local `sqlite+aiosqlite:///./warble.db` if unset.
To run against Supabase/Postgres, set it to a `postgresql+asyncpg://...` URL.

The collector (the process that actually calls Warble and starts the sim
clock) is separate from the API server:

```bash
uv run python -m app.collector.loop
```

**Do not run this against the real Warble API casually** — the sim clock
activates irreversibly on the first non-`/me` call and runs for 7 sim-days.
See [`CLAUDE.md`](CLAUDE.md).

Run tests:

```bash
cd backend && uv run pytest
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env         # VITE_API_BASE_URL, defaults to http://localhost:8001
npm run dev                  # http://localhost:5173
```

`npm run build` produces `frontend/dist`; in production the backend serves
this directly (see `FRONTEND_DIST_DIR` in `backend/app/main.py`) so the whole
app is one Railway/Render service on one origin.

## Breakout detection logic

The detector (`backend/app/detector/`) is entirely pure and deterministic —
no DB or network access, testable with synthetic sample lists alone
(`backend/tests/detector/`). It runs in three layers:

1. **Momentum scoring** (`momentum.py`) — for each pair of consecutive
   samples, computes velocity (views/sim-hour), how that compares to the
   post's own early trajectory, and how it compares normalized by the
   creator's follower count ("reach velocity"). A composite score blends
   both normalizations so a small creator tripling their views scores higher
   than a mega-creator's equivalent raw bump.

2. **Scale-aware volume gate** — an interval only counts as a real signal if
   it clears *either* an absolute-gain floor (a big post adding +40k views,
   even at a modest %) *or* a relative-growth threshold paired with a small
   minimum absolute gain (a small post's real spike, not a 5→50-view
   statistical blip). See "a bug we caught" below for why this is an OR, not
   an AND.

3. **Sustained-confirmation state machine** (`states.py`) — a post has to
   qualify on *several consecutive checks in a row* before advancing
   `NEW → WATCH → RISING → BREAKOUT`. A single good reading only reaches
   WATCH; it takes a streak to reach BREAKOUT, and the streak resets on any
   non-qualifying interval (`COOLING`). This is deliberately conservative:
   one spike could be a bot, a reshare, or a fluke, and one false alert costs
   real trust (and a chunk of the 200/day alert budget) that a slightly
   later, confirmed alert doesn't.

Alerts fire the moment a post's live-sampled state reaches `BREAKOUT`
(`backend/app/collector/loop.py` → `backend/app/alerts/alerter.py`), gated by
two dedupe layers (the local `alerts` table, and an in-process cache) so a
post is never reported twice, and by the request budget, so an alert that
can't be sent right now is queued for the next tick rather than dropped.

## Two real bugs, found and fixed during development

**1. Duplicate-timestamp samples collapsing real momentum to zero.**
The cache-sourced discovery sweep and the live-sampling loop can both land a
reading at the same `sim_hours` (or loop-timing can write two rows in the
same tick). Before the fix, `compute_interval_signals` treated every row as
its own interval — including the phantom, zero-duration interval between two
same-timestamp rows. That interval's gain was zero (or even negative, if the
duplicate rows landed out of order), which scored 0 and broke the state
machine's consecutive-confirmation streak, even when the underlying growth
was a genuine, sustained breakout. The fix
(`_dedupe_samples` in `backend/app/detector/momentum.py`) collapses same-
timestamp rows to one point (keeping the max views seen), so every emitted
interval reflects real elapsed time and real growth.

**2. A relative-growth threshold that didn't scale to large posts.**
The original volume gate required an interval to clear *both* an absolute
view-gain floor *and* a fixed relative-growth percentage. That works for
small posts, but a large post adding a genuinely huge number of views
(+40k) can be well under a 15% relative-growth threshold once its view count
is already large — so real breakouts on a brand's biggest posts were
silently rejected by a threshold that made sense at small scale but not at
large scale. The fix changed the gate to an OR: a large absolute gain alone
is enough, *or* meaningful relative growth paired with a small minimum
absolute floor (so a tiny 5→50-view spike still can't qualify on percentage
alone). See `backend/app/detector/config.py` and `momentum.py`.

Both fixes, and the reasoning behind them, are also recorded in
[`docs/DECISIONS.md`](docs/DECISIONS.md), along with a third issue (an
alert/post foreign-key ordering bug on startup) that was caught by reasoning
through a fresh-restart scenario rather than by a failing test — SQLite
doesn't enforce the foreign key that Postgres does, so it would have passed
every test we had.

## The LLM agent

`backend/app/api/agent.py` backs the dashboard's "Marketing Agent" chat
panel. The design is deliberately narrow:

- **Python computes every fact.** Program totals, alert history, breakout
  history, the selected post's evidence, and top movers are all computed
  server-side from the same stored samples the dashboard uses, then handed
  to the model as a JSON blob (`build_facts`). The model has no DB access, no
  tools, and can't calculate — it only narrates what the given facts mean.
- **It never decides.** The system prompt explicitly forbids declaring a
  post "is a breakout" or "should be boosted" — the deterministic detector
  already decided that; the agent frames everything as a consideration
  ("worth considering," "you may want to").
- **Grounding is enforced, not just prompted.** Every reply is checked
  against two guardrails before being shown: `_numbers_are_grounded` rejects
  any number in the reply that isn't traceable to a number actually present
  in the facts (a rounded restatement is fine; an invented one is not), and
  `_status_is_consistent` rejects a reply that contradicts the selected
  post's real canonical status.
- **Deterministic fallback, always.** If `ANTHROPIC_API_KEY` isn't set, the
  `anthropic` package isn't installed, the API call fails or times out, or a
  reply fails a guardrail, the agent falls back to `deterministic_answer` —
  hand-written, evidence-grounded prose built from the same facts, routed by
  a simple keyword match on the question. The product stays honest and
  useful even with no LLM wired up at all.

The model used is `claude-haiku-4-5-20251001` — fast and cheap enough for a
chat sidebar, called only on-demand per message, never in the collector's
hot path.

## How AI tools were used

This project was built with Claude Code as a pair-programming collaborator,
under the constraints in `CLAUDE.md`: the model wrote and reasoned about
code (collector, detector, alerter, API, frontend, agent) but never executed
anything that would call the real Warble API — the sim clock activates
irreversibly on first non-`/me` request, and the 250-req/rolling-hour budget
is real and shared. Verification against the live API (probing `/me`,
confirming response shapes, checking rate-limit headers) was run manually by
the human and pasted back in, rather than run autonomously. Design decisions
— the OR-gated volume threshold, the dedupe fix, the sustained-confirmation
state machine, the agent's grounding guardrails — were explained and
reasoned through as part of the build (see `docs/DECISIONS.md`), not applied
silently.

## Known limitations

- **In-memory chat session storage.** `agent.py`'s `_SESSIONS` dict holds
  conversation history per `session_id` in process memory only. It doesn't
  survive a server restart and doesn't work across multiple backend
  instances. This was an intentional trade-off (see the comment in
  `agent.py`): a chat is a working conversation, not a record, and the facts
  it reasons over are recomputed fresh every turn anyway.
- **Forward-only alerting after the detector fix.** `POST /alerts` only
  fires from the live collector loop, evaluating the *current* detector
  logic against posts *as they're sampled going forward*. The Breakout Log
  page replays the current detector over every post's full stored history,
  so a post that broke out under older detector logic (before a fix like the
  two above landed) will correctly show up there with its real breakout
  moment — but it was never retroactively alerted, because the alert-firing
  path only ever runs forward from "now." This is visible in the log itself:
  a breakout entry can have no matching alert.
- **Detector thresholds are best-effort defaults, not calibrated.** Every
  constant in `backend/app/detector/config.py` is a reasoned starting point
  against the product brief, not a value tuned against real Warble traffic
  distributions (none were available ahead of time).
- **SQLite in dev enforces less than Postgres in prod.** The alert/post
  foreign-key bug in `docs/DECISIONS.md` is a concrete example: code that
  passes every test locally can still behave differently against the real
  production database. Nothing currently closes that gap beyond awareness of
  it.
