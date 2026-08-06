# Social Media Platform Monitor

**Content breakout detection for brand-creator programs on social media**

---

**Deployed:** [Open Project](https://shortlist-warble-monitor-production.up.railway.app/)

**Walkthrough:** [Notion](https://shortlist-assessment.notion.site/Product-Decisions-Experiments-Shortlist-s-Take-home-3b3658fa60068062bbc9db533037efda?pvs=73)

---

## What this is

LongSheet runs a ~40-creator program on Warble. View counts move in real
time, and the window to act on a breakout closes fast once a post takes
off. This watches every post continuously, decides what counts as real
momentum vs. a good afternoon, and pages the brand only when it's worth
boosting spend behind, resharing, or locking a creator's next post in at
today's rate.

The hard part was never "poll an API on a timer." It's deciding, from
sparse samples, what's signal, and being able to defend that call later.

---



## Non-functional requirements

- **Rate limits:** stay under 250 requests/rolling hour; self-throttle
off the response rate-limit headers and back off on 429/500.
- **Restart-safe:** alert state rehydrates from `GET /alerts` + the local
DB on boot, so a redeploy can't create a duplicate or a missed alert.
- **Graceful degradation:** drop 404'd posts, handle batch
silent-omission (requested ≠ returned) without failing the whole tick.
- **Always-on:** the collector runs unattended for the full 7-day
simulation window — no serverless cold starts.
- **Sim-clock discipline:** all time math uses `metrics_at` deltas, never
wall-clock time.
- **Observable:** every API call and the rate-limit state at the time of
the call are logged.

---



## Architecture

```
Collector  →  Supabase  →  Detector  →  Alerter  →  Read API + Frontend + Agent
 (polls)      (stores)     (scores)     (fires)     (FastAPI)     (React)
```


| Piece                           | Job                                                                                                                                                                                                       |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Collector**                   | Polls Warble on a schedule: discovery every ~6h, live metrics every 15min. Stays under the 250 req/hr limit. Runs 24/7 on Railway. Every reading is appended, never overwritten.                          |
| **Detector**                    | Stateless: recomputes a post's status from its full history every time. Requires *sustained* acceleration across multiple checks, not one spike. Qualifies on absolute gain OR relative growth, not both. |
| **Alerter**                     | Fires `POST /v1/alerts` only on a confirmed breakout, deduped so nothing pages twice.                                                                                                                     |
| **Read API + Frontend + Agent** | Sit on top, display what the detector already decided, and let the marketing agent narrate it. Never touch detection logic directly.                                                                      |


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

docs/                      # product spec, UX principles, decision log, verification notes
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
cp .env.example .env   # VITE_API_BASE_URL — points the dev server at the backend
npm run dev
```

The `.env` step is required in local dev: there's no Vite proxy, so without
`VITE_API_BASE_URL` the browser requests `/api/...` from the Vite origin and
gets nothing. In production it's deliberately empty — the API and the built
frontend are served from one origin by one process (`Dockerfile.web`).

**Collector** (separate process — it must not share one with the API)

```bash
cd backend
uv run alembic upgrade head
uv run python -m app.collector.loop
```

---



## What "starting to move" means

Every reading is turned into an *interval* — the growth between two
consecutive samples of the same post. An interval **qualifies** when both
of these hold:

1. **It moved enough to matter.** Either a large absolute gain
  (≥ 500 views), *or* meaningful relative growth (≥ 15%) paired with a
   small-number floor (≥ 100 views). Either/or, not both — a post at 1M
   views adding 40K is a real breakout at only 4% growth, while 5 → 50
   views is 900% and still noise.
2. **It's fast for this post and this creator.** A composite score, half
  from the post's pace against its own early trajectory, half from views
   per hour per follower. A 10K-follower creator and a 1M-follower
   creator can't be judged on the same raw numbers.

Then a state machine requires that to **hold**:

```
NEW ──qualifies──▶ WATCH ──2 in a row──▶ RISING ──2 more──▶ BREAKOUT
 ▲                                                              │
 └────────────────── any interval fails ◀──── COOLING ◀─────────┘
```

Four consecutive qualifying intervals from a cold start. One good reading
proves nothing; plenty of posts spike and fade. A post that stops
qualifying drops to COOLING and has to re-earn its way back up.

**Two different bars, on purpose:**

- **Official alerts** use the strict, confirmed rule above. A false alert
costs more trust than a slightly late one.
- **The in-app attention queue** ranks by pace *relative to a creator's
usual*, a deliberately softer bar, so there's something worth looking at
even on a quiet day. Softer, not absent: a comparative multiple is
withheld entirely unless the movement behind it clears a noise floor,
so a trivial gain over a near-flat baseline can't read as a big
multiple.

**"Did it ever break out" is not "is it breaking out right now."**
Alerting replays each post's full stored history and reports the *first*
moment it crossed into BREAKOUT. Momentum fades between checks, and a post
that has cooled by the time we look is still one the brand needed to hear
about.

---



## What I optimized for

- Getting detection right, over shipping fast
- A trustworthy, auditable system: deterministic code decides, the LLM
only explains, every AI claim traces to a real number or gets thrown out
- One tight product slice over a broad platform



## Scope

Four screens, each answering one marketer question, nothing more:

- **Home** — what changed, what needs attention now
- **Posts** — the complete tracked set, for when you want to browse
rather than be told
- **Creators** — who's in the program and who's performing
- **Breakouts** — the full history of what's taken off, and whether
it was alerted live



## What I skipped intentionally

- Any comparison/reporting surface beyond what's on Post detail — not
what someone checking twice a day needs first
- Campaign management, budgets, contracts, ROAS — Warble doesn't
provide this data, so building it would mean fabricating

---



## What marketers need vs. what this gives them

A marketer managing 40+ creators doesn't want a dashboard; they want to
be told what changed and what to do about it. Home opens with a
plain-language briefing, not a KPI grid. Post detail answers "should I
act on this" in order: status → real growth chart → why it matters →
a suggested next step, framed as a consideration, never an instruction.

---



## The marketing agent

A conversational agent in the side panel understands and responds to user's natural language. It only sees numbers already computed, with no DB access and no tools, so it can explain what's happening but can't invent a stat or override the detector's decision.

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



## How Claude and Cursor helped

Built with Claude Code inside Cursor. AI wrote most of the code; I directed every scope decision, reviewed every diff and did the data investigation myself, replaying the detector against real stored history before asking Claude Code to implement each fix.

---



## What I'd watch out for at scale


| Concern       | At 40 creators                    | At scale                                                         |
| ------------- | --------------------------------- | ---------------------------------------------------------------- |
| Rate limits   | Comfortable under 250/hr          | Needs tiered polling: fast-moving posts checked more often       |
| Detector cost | Cheap to recompute full history   | Cache last state, compute deltas instead of replaying everything |
| Agent memory  | In-process, fine for one instance | Move to Redis/DB for multiple replicas                           |
| Alert dedup   | Single collector, in-memory set   | Needs a distributed lock or single source of truth               |


---



## What I learned

A detector that passes its own tests can still be silently wrong; the only fix is checking it against real data by hand. I'm also more convinced the deterministic/AI split is the right shape here: AI is more useful and safer for explaining a decision than making one.

---



## Known limitations

- A temporary collector interruption created a gap in the simulation
history, so performance and alert timing during that period are
incomplete.
- Some historical breakouts were identified through replay after they
occurred, so their original alert latency cannot be recovered.
- A post's baseline pace is set from its first two readings and never
  updates, an unusually fast or slow start can skew how that post
  compares to itself later on.
- API activity is logged, but automated collector-liveness alerts are not
yet implemented.
- Marketing Agent conversations reset when the service restarts.
- Creator-relative ranking would benefit from further tuning against a
complete dataset.

---

© 2026 Sakshi Karande. Built for the Shortlist take-home assessment.