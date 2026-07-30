# Product: LongSheet Breakout Monitor

## Who it's for
You're the social media manager at LongSheet (custom bedding), running a
~40-creator program on Warble. You check this ~twice a day. It tells you
what moved, what deserves attention, and why.

## The job to be done
The moment a post gains momentum is the moment the brand can act: boost it,
reshare it, or extend the creator's deal. A day late and the moment is gone.

## What "breakout" means (draft — refine in detector)
Not raw views. Momentum = rate of change, normalized per creator and post age.
A small creator tripling in 3h matters more than a mega-creator ticking up.
A true breakout deviates UPWARD from the expected decay curve for its age.

## The three plays (map detection → action)
- **Boost** (paid spend): proven organic momentum, not yet peaked. Time-critical.
- **Reshare** (brand channels): performing well, lower urgency.
- **Extend deal** (re-sign creator): the creator is hot → lock next posts at today's rate.

## Dashboard = opinionated briefing, not a data table
- Top: "What deserves attention now" — ranked, each with the why + recommended play
- Per-post trajectory sparkline (show real sparse samples honestly)
- Breakout inbox (mirrors GET /alerts): what we caught, how early
- System health: requests used, watchlist size, budget spend (shows we're observable)
- "Program pulse": weekly summary — which creators over-deliver, which angles win

## Speed = money
Frame latency as dollars: caught this ~2h after it started climbing, while
still rising = boost into a rising post, not a dead one.

## Soft Requirements

### Functional
- Collect post metrics over time, persist as append-only time series
- Discover new posts as they land; enroll in watchlist
- Score momentum per post; detect breakouts
- POST /alerts once per breakout, deduped
- Dashboard: attention briefing, trajectories, alert inbox, system health
- (Optional) LLM narration: why it broke out + recommended play

### Non-functional
- Stay under 250 req/rolling hour; self-throttle on rate-limit headers
- Survive restarts (rehydrate alert state from GET /alerts + local DB)
- Graceful degradation: back off on 429/500, drop 404'd posts, handle
  batch silent-omission (requested ≠ returned)
- Run unattended for the sim duration (always-on deploy)
- All time math in sim-clock, never wall-clock
- Observable: log every API call + rate state