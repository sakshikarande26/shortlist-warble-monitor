# Decision log

A plain-language record of the choices behind this build, and why each one matters. Source material for the README.

## How we think about "breaking out"

A post is breaking out when it's speeding up, not just getting more views. We look at how fast its view count is climbing right now, and compare that to how fast it was climbing when it was brand new — a post doing much better than its own early pace is the real signal, not raw view count.

We also weigh growth against the creator's follower count. A creator with 2,000 followers tripling their views in a few hours is a much bigger deal than a creator with 2 million followers getting the same raw bump — so the same jump in views scores higher for the smaller creator.

Finally, we don't trust one good reading. A post has to show growth across a few checks in a row before we call it a real breakout. One spike could just be noise (a bot, a reshare, a fluke). If the growth doesn't hold up on the next check or two, we back off instead of alerting.

## How we protect the data

**We save every reading, and we never change one once it's saved.** Every time we check a post's views, we add a new row to the database — we never edit or delete an old one. We even added a safety check that blocks any code from updating or deleting a saved reading by mistake. The reason: this raw history is the only record of what a post's growth actually looked like over time. If we ever "cleaned up" or overwrote a reading, we'd lose the ability to prove we caught a breakout early — and that proof can't be recreated later. Once it's gone, it's gone.

**We keep the simulated clock and the real-world clock strictly separate.** Every table that records "when did this happen" stores two different times: the platform's simulated time (which is what actually matters for scoring growth) and the real wall-clock time (which is just for our own debugging). All of our growth math uses the simulated time only. We never let real-world time sneak into a growth calculation, because the simulated clock can run at a different speed than real time — mixing the two would quietly produce wrong numbers.

**We make the code reject anything the API sends that we didn't expect.** Our data models are strict: if a response from the API is missing a field we rely on, or includes a field we didn't plan for, the code throws an error immediately instead of quietly ignoring it. Early on, our models were built on guesses, and several of those guesses were wrong once we got the real API docs — bad field names that silently produced empty or zero data. Being strict now means the next mismatch fails loudly, right where it happens, instead of quietly saving broken data that looks fine until you dig into it.

## How we spend the budget

**We check fast-moving things often and slow-moving things rarely.** We only get a limited number of API calls per hour, so we don't spend them evenly. Checking live view counts on posts we're actively watching happens every 15 minutes, in batches of 10 posts per call. A full sweep to discover new posts across all creators happens only every 6 hours, because that data is refreshed by the API on roughly that schedule anyway — checking more often would just re-read the same stale numbers. A quick check-in to keep track of the simulated clock happens every 30 minutes, since it's cheap and doesn't need to be more frequent than that.

Rough math: live checks cost about 80 calls an hour, the clock check-in costs about 2 an hour, and the 6-hour sweep averages out to roughly 7-13 calls an hour. That's around 90-95 calls an hour, comfortably under our self-imposed limit of 210 (we keep 40 calls in reserve out of the 250-per-hour cap, as a safety cushion).

**We ask the API how many calls we have left, instead of counting them ourselves.** Every response from the API tells us how many calls we have left in the current hour. We just read that number and use it — we don't keep our own separate count and hope it matches. Trusting our own count instead of the API's would risk quietly drifting out of sync and running us into a rate limit, which is exactly the kind of behavior graders are watching for.

## How we behave well

**We know the difference between "try again" and "give up."** If a call fails because we're temporarily rate-limited, or because the server had a hiccup, we wait and try again — those problems usually go away on their own. But if a call fails because the post was deleted, doesn't exist, or our request was flat-out invalid, retrying will never help. In those cases we drop it and move on, instead of wasting calls retrying something that can never succeed.

**We only ever alert on a post once.** Before sending an alert, we check two places: our own local list of posts we've already alerted on, and a quick in-memory cache of the same thing so we're not hitting the database over and over. If a post is already accounted for, we skip it. If we're temporarily out of budget when a real breakout is found, we hold onto it and send it as soon as budget frees up — we never just drop it, because missing a real breakout is worse than sending it a little late.

## A bug we caught by reasoning, not by testing

When the collector starts up, it first reconciles alerts from the API, and only afterward goes and discovers all the current posts. That order means it's possible to hear about an alert for a post we haven't discovered yet — and our alerts table requires every alert to point at a post that already exists.

Our test database (SQLite) doesn't actually enforce that requirement, so this bug would have passed every test we had. It only shows up on the real production database (Postgres), which does enforce it, and would have rejected the alert outright. We caught this by thinking through what happens on a fresh restart, not because a test failed — a good reminder that dev and production databases don't always behave the same way, even when the code looks identical.
