# Final Review — verification log

Pre-submission pass. Every line below was verified by running something,
not by reading code. Commands and their real output are included. Where I
could not verify a thing from this environment, it says so and tells you
exactly how to check it yourself.

Verified against the live Supabase database and the deployed service on
**2026-08-05 ~23:30 UTC**, at sim hour **137.4 of 168 (Day 6 of 7)**.

---

## 0. Headline

Five defects found. Four were silent — nothing errored, the system just
produced a wrong number or failed to do something it was supposed to do.

| # | Defect | Severity | Status |
|---|---|---|---|
| 1 | Only 3 of 10 breakouts ever reported to `POST /v1/alerts` | **Critical — this is the scored mechanism** | Fixed, dry-run verified |
| 2 | Breakouts on removed posts excluded from detection entirely | High | Fixed |
| 3 | Half of all collected samples invisible to the detector | High — costs latency | Fixed |
| 4 | A 4-view gain ranked #1 on the momentum board as "8.4× pace" | High — precision/trust | Fixed |
| 5 | Agent guardrail rejected correct answers; replies truncated mid-word | Medium | Fixed |

**The single most important thing:** fixes 1 and 2 are **not deployed yet**.
Until the collector service runs this code, those 7 alerts do not exist on
Warble's scoreboard. See §7.

---

## 1. Alert recall — the scoreboard

### The defect

`loop.py` asked the detector which posts are in `BREAKOUT` **at this
instant**:

```python
breakouts = {pid: ev for pid, ev in evaluations.items() if ev.state == "BREAKOUT"}
```

The tick runs every 15 minutes. Momentum fades faster than that. A post
that broke out and cooled in between was never reported — and at the moment
I checked, **zero** posts were in `BREAKOUT`, so a run of that code would
have alerted on nothing at all.

### Evidence

Replaying the current detector over stored history in the live DB:

```
posts tracked                        : 211
EVER reached BREAKOUT (replay)       : 10
CURRENTLY in BREAKOUT                : 0
alerts recorded locally              : 3
BROKE OUT BUT NEVER ALERTED          : 7
```

Recall was **3/10 = 30%**. Among the misses, from `GET /api/breakouts`:

```
wp_288ee759f3 @jordan.haddad        284,510 -> 720,022 views  (2.5x)  alerted=False
wp_4ca8426214 @theo.furandfurniture 454,570 -> 771,647 views  (1.7x)  alerted=False
wp_43a9256698 @ninafamilydays        18,072 ->  42,346 views  (2.3x)  alerted=False
wp_3d803cebff @amara.softglam        65,547 -> 131,751 views  (2.0x)  alerted=False
wp_1047778c8d @byelenao           1,091,002 -> 1,146,495 views (1.1x) alerted=False
wp_bb0b6a43ea @bymarcusp           228,757 -> 326,511 views  (1.4x)  alerted=False
wp_5298cb6e59 @byivyn               32,686 ->  40,166 views  (1.2x)  alerted=False
```

A post that climbed 2.5× to 720K views was never reported.

### The fix

`detector/evaluate.py` — `find_breakouts()` replays each post's full stored
history and returns the **first** moment it crossed into BREAKOUT. The
detector's decision rule is untouched: same thresholds, same state machine,
same four consecutive confirmations. Only the window we look through
changed, from the latest state to the whole history.

`alerts/alerter.py` now stamps `decided_sim_hours` with the moment the post
*actually* broke out rather than the moment the tick noticed.

Idempotency is unaffected — `alerts.post_id` is the primary key, and the
alerter dedupes against that table before spending a request. Re-offering
an already-reported post every tick costs nothing.

### Dry run against production data

```
find_breakouts over ALL posts  : 10
already alerted                : 3
=== WOULD FIRE ON NEXT TICK: 7 new alerts ===
  wp_3d803cebff  @amara.softglam        broke out at sim   3.966  status=gone
  wp_4ca8426214  @theo.furandfurniture  broke out at sim   5.967  status=active
  wp_5298cb6e59  @byivyn                broke out at sim   7.968  status=active
  wp_bb0b6a43ea  @bymarcusp             broke out at sim   8.468  status=active
  wp_43a9256698  @ninafamilydays        broke out at sim  10.469  status=active
  wp_288ee759f3  @jordan.haddad         broke out at sim  10.469  status=active
  wp_1047778c8d  @byelenao              broke out at sim  25.821  status=active
```

**Recall 3/10 → 10/10.** Alert budget cost: 7 of 200/day.

These alerts are **late by construction** — they carry the real breakout
moment but are submitted now. Recall is recovered; latency for these seven
is not.

### Second instance of the same mistake

The sweep ran over `get_watchlist_post_ids()`, which is `status='active'`
only. `wp_3d803cebff` broke out at sim 3.97 and was removed at sim 9.47, so
it was excluded from detection along with sampling. A post that broke out
before it came down still broke out. Detection now runs over
`get_all_post_ids()`; sampling still (correctly) skips removed posts, since
polling a dead post buys a reading that will never change.

Also fixed: `_live_sample_tick` returned early when the watchlist was
empty, skipping detection entirely. Detection reads stored history and
doesn't need anything new to have been sampled.

### Tests

`tests/detector/test_evaluate.py`, `tests/collector/test_loop.py`:
a cooled-off post still reports its breakout; the first breakout wins over
a later one; a removed post's breakout still alerts; repeated ticks never
double-alert; a post that never broke out never alerts.

---

## 2. Sample resolution — latency

`sim_hours` was taken from `/me`, polled every 30 minutes, while live
sampling runs every 15. Two genuinely different rounds got stamped with the
**same** timestamp, and `_dedupe_samples` then collapsed one away.

```
distinct sim_hours vs raw sample count:
  wp_8feb71135e  raw=283  distinct_hours=151
  wp_69a07ac8de  raw=283  distinct_hours=151
```

Half the resolution the request budget had already paid for, and every
breakout confirmed roughly one full round later than the evidence allowed.
Latency is scored.

Fixed in `CollectorState`: anchor the sim clock at each heartbeat and
interpolate between anchors using the server's own `clock_multiplier`.
Costs no extra requests; every heartbeat re-anchors so error can't
accumulate.

Verified the clock multiplier is **1.0×** (sim time == real time):
first request 2026-07-31 06:00:51 at sim 0.032; now 2026-08-05 22:40 at sim
136.691 — 136.67 real hours elapsed for 136.66 sim hours.

---

## 3. Ranking precision

`GET /api/posts` ranked this post **#1**:

```
@june.patel  Worth watching  pace=8.403  gain=4  streak=0
```

Its own detail endpoint disagreed with its label:

```
status_label: Worth watching | detector state: NEW | reason: below_volume_floor
absolute_gain: 4          relative_growth_pct: 0.12
window_hours: 0.476       consecutive_qualifying_checks: 0
creator_pace_ratio: 8.403 creator_pace_basis: self
```

The detector had gated that interval out as `below_volume_floor`, and the
presentation layer sold it as 8.4× momentum anyway. Dividing a 4-view gain
by a near-flat baseline makes a big, precise-looking, meaningless number.

Fixed with a noise floor on the comparative ranking (`_MIN_RANKABLE_GAIN_VIEWS
= 25`, `_MIN_RANKABLE_GROWTH_PCT = 0.5`). Below it the multiple is withheld
(`None` → "not enough history"), exactly as `_sane_ratio` already does for
degenerate baselines. That one change propagates everywhere: label, pace
column, ranking, and the agent's facts.

These are deliberately far below the detector's own floor (500 views) —
the in-app queue is meant to be a softer bar than official alerts, per the
README. Softer, not absent. **Detection is not affected.**

After:

```
@byelenao          Worth watching  pace=1.91  gain=404   growth%=2.81
@byelenao          Worth watching  pace=1.68  gain=2047  growth%=5.96
@amara.softglam    Worth watching  pace=1.60  gain=157   growth%=1.86
...
wp_a0c3161228 -> status_label: Steady | pace_ratio: None | gain: 4
```

---

## 4. The marketing agent

### Marketer point of view

The agent spoke as the system, not to the marketer. It was handed
`alerts` / `submitted` / `alert_sent` and dutifully echoed them back as
"an alert has been sent for this post", and one of its four suggested
prompts was *"What have we alerted on so far?"*.

Renamed through the whole path — facts payload (`flagged_posts`,
`was_flagged`, `flagged_on`), system prompt, deterministic fallbacks,
reference-card chips ("Flagged Day 3" / "Not flagged yet"), and the prompt
chip (now *"What's proven out this week?"*). The model echoes the
vocabulary it is handed, which is why the payload rename mattered more than
the prompt rule.

Also added a rule against quoting raw field names, plus a rewrite pass
(`_despecify_field_names`) that turns a leaked `post_count` into
"post count". It is an explicit allow-list of our key names, **not** a
general snake_case rule — post ids contain underscores and mangling
`wp_7555c0d8c7` would corrupt a real identifier the reader may want to
search on. Cosmetic only: it runs *after* the guardrails, so what gets
grounding-checked is exactly what the model produced.

### Guardrail false positive

`_status_is_consistent` rejected **any** mention of a canonical status
other than the selected post's — anywhere in the reply. Asked *"how does
that compare to the rest of the program?"*, the model correctly said the
selected post was steady while others were worth watching, and the whole
reply was thrown away:

```
agent reply rejected: contradicts status Steady
```

Now scoped per sentence: a sentence may name a different status when it
plainly concerns something else (it names another creator's handle, or
reads comparatively). The guarantee that matters — a sentence asserting a
status *about the selected post* must assert the real one — is intact and
tested both ways.

### Truncation

Two replies were cut off mid-word ("...the shape of", "...similar multi").
Root cause, from the raw API response:

```
stop_reason: end_turn
usage: output_tokens=487, output_tokens_details(thinking_tokens=302)
blocks: [('thinking', 0), ('text', 531)]
```

`claude-sonnet-5` returns a thinking block that shares the `max_tokens`
budget with the visible reply. At 700 there wasn't reliably enough left for
both halves, and the REASONING half comes second. Harmless while reasoning
was computed and then dropped by the UI; very visible once rendered.
Raised to 3000, plus `_call_llm` now refuses to return a reply whose
`stop_reason` is `max_tokens` — half a strategic read is worse than none.

### Reasoning was never rendered

The backend generated it, `agentChat.tsx` stored it, `AiPanel`'s `Turn`
never displayed it. The README described it as visible. Now rendered
between the reply and its evidence cards.

### Live agent verification — 9 varied questions, all grounded

All returned `llm_available: true`, no fallbacks, no truncation:

| Question | Result |
|---|---|
| "Which creator has the most posts?" | "jordan.haddad, with 14 tracked" — correct, read from roster |
| "byelenao has a post past a million views — what happened?" | Correct: Day 2 breakout, 1.09M → 1,146,495, now Steady |
| "Draft a two-sentence Slack update" | Grounded, real handles and numbers, no invented budget/contract |
| "What's proven out this week?" | Cross-referenced breakout history with real multiples |
| "Tell me about post wp_7555c0d8c7" | **Digits-in-post-id guardrail: no false positive** |
| "Sustained or a spike?" (selected post) | Correct comparative read |
| "What's the weather in Paris?" | Declined gracefully, one sentence |
| "How is @totally_not_a_real_creator doing?" | Did not hallucinate; said it isn't in the roster |
| Multi-turn follow-up | Session memory worked; comparative answer no longer rejected |

Headline: `"byelenao's 1.1M-view post dominates week"` — grounded, no alert
mention.

---

## 5. Everything else verified

| Requirement | Status | Evidence |
|---|---|---|
| Warble auth + `/me` heartbeat | **Done** | 159 successful `/me` calls in `request_log`, last at sim 137.389 |
| Discovery sweep + pagination | **Done** | 40 creators, 211 posts upserted; 39 sweeps per creator endpoint logged |
| Live batch collection | **Done** | 4,549 successful `GET /posts/batch`; 52,030 samples, `source` in {cache, live} |
| Post removal → `status="gone"` | **Done** | `wp_3d803cebff` gone at sim 9.468; unit-tested |
| Momentum/baseline scoring | **Done** | `tests/detector/test_momentum.py` passes |
| Breakout state machine | **Done** | `tests/detector/test_states.py` passes; traced `wp_7555c0d8c7` through real history (breakout sim 54.36, 37,890 → 46,057) |
| `POST /v1/alerts` really called | **Done** | 3 rows in `request_log` with `endpoint='/alerts', method='POST', status=200`; 3 rows in `alerts` |
| Idempotency / reconciliation | **Done** | `post_id` is PK; `sync_alerts` tested; no duplicates in live DB |
| Rate-limit self-throttling | **Done** | 107 requests in the last rolling hour vs 250 cap; `X-RateLimit-Remaining` recorded on every logged call |
| Comparative ranking + labels | **Done** | Verified live; `test_routes.py` passes |
| `GET /home`, `GET /posts` | **Done** | curl'd, real data, ranking monotonic |
| Creators roster + detail | **Done** | 40 creators; `wc_a94a65edfc` → 13 active posts, median 69,223 views |
| Breakout log | **Done** | 10 entries with real multiples |
| 404 handling | **Done** | Unknown post and creator both 404 |
| Frontend build | **Done** | `tsc -b && vite build` — zero errors |
| SPA routes hard-refresh | **Done** | All 7 routes → 200; assets 200 |
| Backend tests | **Done** | **105 passed** |
| `request_log` populated | **Done** | 6,320+ rows |
| Fails loudly without config | **Done** | `ValidationError: warble_api_key Field required` |
| No secrets in frontend/git | **Done** | No key literals in any tracked file; `.env` never committed; only `.env.example` ever added |
| Fresh clone works | **Fixed** | `frontend/.env.example` is tracked but the README never said to copy it, and there is no Vite dev proxy — a fresh clone's dev frontend could not reach the API. README now documents it, plus the collector run command, which was also missing. |
| Migrations from scratch | **Done** | `alembic upgrade head` on an empty DB builds all 6 tables; `posts` has `status` + `gone_sim_hours` |

Smaller correctness fixes:

- `is_duplicate` was set on *any* re-record, so startup reconciliation
  marked all three of our own real alerts as duplicates. Now only the API's
  own verdict sets it.
- Unknown `/api/*` paths fell through to the SPA catch-all and returned
  200 + HTML, which `fetch()` then failed to parse as JSON. Now a real 404.
- `evaluate_posts` did one query per post — 211 sequential Supabase round
  trips per tick, a statement-timeout risk. Now one bulk query, the same
  fix `routes._samples_by_post` already had.

---

## 6. The outage — disclosed, not hidden

The collector was **down for 67 of the window's 168 hours**.

```
sim 68.322  last sample before gap   2026-08-03 02:23 UTC
sim 135.668 first sample after gap   2026-08-05 21:39 UTC
```

~2.8 days in the middle of a 7-day run with nothing collected and nothing
alertable. Recall and latency for anything that broke out in that window
are gone and cannot be recovered. This is visible in the data, so the
README now states it plainly under Known limitations rather than leaving it
to be found. The restart was manual; a liveness check on the collector
service is the first thing I would add next.

This is also the answer to "the site isn't updating as the collector
collects": the collector was dead, not the dashboard. Both are current now
(dashboard `last_checked_sim_hours` 137.389 matches the DB exactly).

---

## 7. What I could NOT verify — you must check these

**1. The fixes are not deployed.** This is the one that matters.

```
$ git status -sb
## main...origin/main [ahead 1]      # plus all of today's changes uncommitted
$ curl https://shortlist-warble-monitor-production.up.railway.app/health
{"status":"ok"}                       # deployed build predates the `db` field
```

The deployed service runs `origin/main`. Until the **collector** service
is redeployed, `find_breakouts` never runs and those 7 alerts are never
sent. With ~30 hours left in the window, this is time-critical.

**2. I never called the Warble API.** Per `CLAUDE.md` I made no request to
`warble.shortlistos.com` — not even `/me`. Every claim about alerting is
from stored data, a dry run, or the existing `request_log`. The 7 new
alerts have **not** been sent; they will fire on the collector's first tick
after deploy.

**3. No browser click-through.** I verified every route returns 200 with
the correct shell and assets, and that the build is clean, but I could not
open a browser to check rendering or the console. Worth five minutes of
your own clicking.

### To verify after deploying

```bash
# collector picked up the fix and fired the backfill
railway logs -s <collector>   # expect: "alerts: 7 fired, 3 deduped, 0 queued, 0 failed"

# Warble's own record now shows 10
curl -H "Authorization: Bearer $WARBLE_API_KEY" \
     https://warble.shortlistos.com/v1/alerts | jq '.data | length'

# and the app agrees
curl -s https://<your-app>/api/status | jq '.alerts_sent'   # expect 10
curl -s https://<your-app>/health                           # expect {"status":"ok","db":"ok"}
```

If the count is not 10, check the collector log for terminal errors on
`wp_3d803cebff` — it is the removed post, and a 404 there is handled,
logged, and dropped by design rather than retried.
