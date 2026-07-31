# Decision log
Running record of my engineering choices + reasoning. Source material for the README.

## Format
- **Decision:** what
- **Why:** reasoning + what we rejected
- **Date/sim_hours:**

## samples is append-only (enforced twice)
**Decision:** No update/delete in DAO + ORM before_update/before_delete raises.
**Why:** Raw trajectory is the evidence recall/latency grading depends on.
Capture is irreversible; detection isn't. Protect the one asset we can't rebuild.

## Idempotency at the schema level
**Decision:** alerts.post_id is PK (not autoinc). record_alert preserves first
decided_sim_hours; repeat calls only flag is_duplicate.
**Why:** Mirrors the API's per-post idempotency. First alert timestamp is what's
scored for latency — local state must never diverge or double-fire.

## sim_hours vs wall-clock separation
**Decision:** Every table carries both. Detection reads ONLY sim-time columns;
wall-clock is ops/debug only.
**Why:** The sim clock advances the world. Wall-clock velocity math would be wrong.

## API Budget tracker reads server headers, not a local counter
**Decision:** BudgetTracker reads `remaining` off Warble's rate-limit header
rather than counting calls locally. Ceiling 250, reserve 40, effective ~210.
**Why:** The server's rolling-hour count is the source of truth; a local counter
would drift and risk 429s (which show up in the traffic they grade).
**Bug caught:** pre-first-call default double-subtracted the reserve (170 vs 210).
Fixed + verified in tests.

## Cadence: 6h discovery / 30min heartbeat / 15min live sampling
**Decision:** Live sampling every 15min (batch-10 ≈ 80 req/hr, the dominant cost);
heartbeat every 30min (cheap, sim-time needs no finer resolution); discovery every
6h (matches the API's cache TTL — sweeping faster just re-reads stale data).
**Why:** ~90-95 req/hr sustained, well under the 210 ceiling, leaving headroom for
retries and hot-post bursts. Rejected uniform fast polling as budget-wasteful.

## Startup ordering FK bug (caught by reasoning, not tests)
**Decision:** sync_alerts() runs before discover(), so a server-known alert can
reference a post not yet in the local DB. Postgres enforces the FK and would reject
it; SQLite doesn't, so local tests would NOT have caught this. Handle via
IntegrityError → warn + skip, reconcile on next sync.
**Why:** Worth noting: this surfaced from reasoning about prod (Postgres) vs dev
(SQLite) behavior, not from a failing test. The kind of bug that only bites in
deployment.

## Loop scheduling is wall-clock; stored sim_hours comes only from /me
**Decision:** The loop's timers run on real minutes (the budget window is
wall-clock), but every stored sim_hours value comes from the latest /me heartbeat.
**Why:** Keeps the two clocks from leaking into each other. Detection math stays
in sim-time; scheduling stays in real-time where the rate limit lives.