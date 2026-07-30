# Shortlist Warble Monitor

Take-home for Shortlist's AI Product Engineering role. Build a monitoring
product that polls the Warble API, detects "breakout" posts, and alerts a
brand (LongSheet, ~40 creators).

## Evaluated on
- Recall: did we catch the posts that broke out
- Latency: how soon after momentum began did we alert
- Precision: how few false alerts
- README + walkthrough quality
- API traffic pattern (they log and read our request behavior)

## Hard constraints
- 250 requests / rolling hour (every admitted call counts, incl. /me)
- POST /alerts: 200/day cap, idempotent per post, first timestamp is final
- Listing endpoint (/creators/:id/posts) cached ~6h → cheap, wide, STALE
- Live endpoints (/posts/:id, /posts/batch) fresh; batch = max 10 posts/call
- ALL timestamps are on a simulation clock (use metrics_at deltas, not wall clock)
- Clock starts on first non-/me request; runs 7 sim-days

## Core strategy
Two-tier adaptive sampling:
1. Cheap wide discovery sweep (cached listings, ~6h cadence) → find/enroll posts
2. Momentum-scored watchlist → prioritize
3. Live batch confirm (dense on hot suspects, sparse on cold)
4. Alert once per post at confidence
Deterministic detector decides alerts. LLM (optional) only narrates "why + play".

## Principles
- Capture is irreversible; detection is not. Persist every sample append-only.
- Read rate-limit headers, self-throttle. Back off politely on 429/500.
- Explain meaningful design decisions as you work (prompt-to-learn, not bypass).

## Stack
FastAPI + httpx (async) + Supabase/Postgres backend. React (Vite+TS) frontend.
Deploy backend always-on (Railway/Render); activate clock only once collector is live.

## API call discipline (STRICT)
- NEVER run scripts or tests that hit the Warble API. The human runs those manually.
- The clock is unactivated. Any call to a non-/me endpoint activates it irreversibly.
- You may write code and tests, but do not execute anything that makes a network request to warble.shortlistos.com.
- Even /me calls cost budget (250/rolling hour) — don't run probes either.
- If you need to verify against the API, ask the human to run it and paste output.