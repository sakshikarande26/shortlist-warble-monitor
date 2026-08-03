<div align="center">

# Social Media Platform Monitor

**Content breakout detection for brand-creator programs on social media**

(Built for the Shortlist AI Product Engineering) 

</div>

---

## What this is

40 creators posting on Warble, view counts moving in real time, and a
window that closes fast once a post takes off. This watches every post
continuously, decides what counts as real momentum vs. a good afternoon,
and pages the brand only when it's worth it.

The hard part was never "poll an API on a timer." It's deciding, from
sparse samples, what's signal, and being able to defend that call later.

---

## Architecture

```
Collector  →  Supabase  →  Detector  →  Alerter  →  Read API  →  Frontend + Agent
 (polls)      (stores)     (scores)     (fires)     (FastAPI)     (React)
```

| Piece | Job |
|---|---|
| **Collector** | Polls Warble on a schedule: discovery every ~6h, live metrics every 15min. Stays under the 250 req/hr limit. Runs 24/7 on Railway. Every reading is appended, never overwritten. |
| **Detector** | Stateless: recomputes a post's status from its full history every time. Requires *sustained* acceleration across multiple checks, not one spike. Qualifies on absolute gain OR relative growth, not both. |
| **Alerter** | Fires `POST /v1/alerts` only on a confirmed breakout, deduped so nothing pages twice. |
| **Read API + Frontend** | Sit on top, display what the detector already decided. Never touch detection logic directly. |

---

## Repo map

```
backend/
└── app/
    ├── collector/
    │   └── loop.py       # the 24/7 polling scheduler
    ├── detector/
    │   ├── momentum.py   # velocity, acceleration: the core scoring math
    │   ├── evaluate.py   # runs the state machine on a post's samples
    │   └── config.py     # every tunable threshold, in one place
    ├── alerts/
    │   └── alerter.py    # fires POST /v1/alerts, dedup + budget-aware
    ├── api/
    │   ├── routes.py     # read endpoints: home, post detail, creators, breakouts
    │   └── agent.py       # the grounded LLM chat endpoint
    └── db/                # models + session handling (Supabase Postgres)
tests/                     # detector, API, agent tests

frontend/
└── src/
    ├── pages/             # Home, Post detail, Creators, Breakouts
    ├── components/        # post cards, charts, the agent panel
    └── lib/
        ├── copy.ts        # every piece of marketer-facing text, one file
        └── api.ts         # typed client for the backend

docs/                      # UX principles + engineering decision log
```

---

## Running it

**Backend**
```bash
cd backend
uv sync
cp .env.example .env   # DATABASE_URL, WARBLE_API_KEY, ANTHROPIC_API_KEY
uv run uvicorn app.main:app --port 8001
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

**Deployed:** https://shortlist-warble-monitor-production.up.railway.app/

---

## What "starting to move" means

A post has to accelerate, and hold that acceleration across two
consecutive checks, before it counts as a breakout. One good reading
isn't enough; plenty of posts spike and fade.

Two different bars, on purpose:

- **Official alerts** use the strict, confirmed rule: a false alert
  costs more trust than a slightly late one.
- **The in-app attention queue** ranks by momentum *relative to a
  creator's usual pace*, so there's always something worth looking at,
  even on a quiet day.

---

## The two bugs I found

Both found the same way: pick a real breakout, run the detector on it
by hand, check the number against what actually happened.

1. **Duplicate samples at the same timestamp.** Cache and live readings
   sometimes landed at the same moment, creating a fake zero-growth
   interval that broke the "sustained growth" streak. A 45× breakout
   was sitting in the data and never fired. Fixed by deduplicating
   samples by timestamp before scoring.

2. **Relative-growth thresholds don't scale.** Requiring both a minimum
   absolute gain *and* a minimum percentage per check works at 10K
   views. At 1M views, adding 40K is a real breakout but only ~4%
   growth, so it silently failed. Fixed by qualifying on absolute gain OR
   relative growth, not both.

**The lesson:** a detector that passes its own tests can still be
silently wrong. The only way to catch that is testing it against
something real, by hand, before trusting it.

---

## What I optimized for

- Getting detection right, over shipping fast
- A trustworthy, auditable system: deterministic code decides, the LLM
  only explains, every AI claim traces to a real number or gets thrown out
- One tight product slice over a broad platform

## What I skipped on purpose

- A full posts/creators browsing app: kept to home, post detail,
  creators, and breakout history
- Any comparison/reporting surface: not what someone checking twice a
  day needs first

---

## Debugging and UX decisions

Early on, the UI leaned on backend concepts: snapshot counts, raw
scores. Rewrote it into marketer language: "taking off," "worth
watching," "not enough history yet." The rule: if a label wouldn't make
sense to someone who's never seen the code, it doesn't belong in the UI.

Also made "one canonical status per post" a hard rule, after catching a
case where a post showed "Act now" in one place and "Watch closely" in
another, computed by two slightly different code paths. Now one
function decides status, every screen reads from it, and a test fails
if that regresses.

## What marketers need vs. what this gives them

A marketer managing 40+ creators doesn't want a dashboard; they want to
be told what changed and what to do about it. Home opens with a
plain-language briefing, not a KPI grid. Post detail answers "should I
act on this" in order: status → real growth chart → why it matters →
a suggested next step, framed as a consideration, never an instruction.

---

## The LLM feature: marketing agent

A chat-style agent in the side panel. It only sees numbers already
computed, with no DB access and no tools, so it can explain what's happening
but can't invent a stat or override the detector's decision.

**Guardrails:** every number in a reply has to trace back to the facts
object given to it, or the reply is thrown out and replaced with a
plain-text summary. Same fallback on API failure or missing key: the
product stays usable, just quieter. Session memory persists per
conversation until the user ends the chat.

**How I'd evaluate it:** does every number trace to a real fact, does
it ever contradict a post's actual status, does it degrade gracefully.
All three are tested. What's missing: an actual marketer reading its
answers and judging usefulness, not just accuracy.

---

## How I used Claude and Cursor

Built with Claude Code inside Cursor, plus a separate Claude
conversation for architecture and debugging discussions. AI wrote most
of the code; I directed every scope decision, reviewed every diff, and
did the actual data investigation that found both detector bugs by hand
before asking Claude Code to fix them.

---

## What I'd watch out for at scale

| Concern | At 40 creators | At scale |
|---|---|---|
| Rate limits | Comfortable under 250/hr | Needs tiered polling: fast-moving posts checked more often |
| Detector cost | Cheap to recompute full history | Cache last state, compute deltas instead of replaying everything |
| Agent memory | In-process, fine for one instance | Move to Redis/DB for multiple replicas |
| Alert dedup | Single collector, in-memory set | Needs a distributed lock or single source of truth |

---

## What I learned

A detector that passes its own tests can still be silently wrong; the
only fix is checking it against real data by hand. I'm also more
convinced the deterministic/AI split is the right shape here: AI is
more useful, and safer, explaining a decision than making one.

---

## Known limitations

- Agent session memory is in-process, clears on redeploy/restart
- Relative-ranking calibration hasn't been tuned against a full 7-day
  dataset, since the window's still open

---

<sub>© 2026 Sakshi Karande. Built for the Shortlist take-home assessment.</sub>
