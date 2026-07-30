# Decision log

Running record of choices + reasoning. Source material for the README.

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