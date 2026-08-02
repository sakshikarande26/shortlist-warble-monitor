---
name: designing-warble-marketer-ui
description: Use when designing or implementing the UI/UX for the Shortlist Warble monitoring take-home — page structure, marketer language, attention prioritization, AI explanations, post detail, and whether a feature is necessary.
---

# Designing the Warble Marketer UI

## Product Goal
Build an AI-native creator-content monitoring product, not a technical dashboard.
Help a marketing manager answer:
1. What happened while I was away?
2. What needs my attention now?
3. Why does it matter?
4. What evidence supports that?
5. What should I consider doing next?

Core promise: turn a stream of creator-post data into a trustworthy attention queue and clear next actions.
Feel: simple, playful, polished, credible for a serious brand team.

## Scope (this build)
Two screens only:
1. **Home** — the daily briefing / attention queue.
2. **Post detail** — reached by clicking any post.
Do NOT build Posts list, Creators page, comparison, settings, or chat. Keep it small and excellent.

## Mental Model
Creator → Post → metric history → momentum → insight → action.
- Creator is context. Post is the main unit.
- Metric snapshots over time are the evidence.
- Momentum/breakout state is derived (deterministic).
- AI explains it in marketer language.
- The marketer decides consequential actions.
Do not let API/DB/code terminology shape the interface.

## Marketer Language (critical)
BAD (never show): metric snapshots, polling cycle, detection threshold, acceleration score, alert payload, baseline deviation, API status, deleted boolean, z-score.
GOOD: gaining momentum, taking off, watch closely, act now, steady, slowing down, updated recently, no longer available, compared with this creator's usual, why this matters, suggested next step.

## Home: The Daily Briefing
Do NOT open with a KPI grid. Open with a concise briefing built from REAL state (never invented):
> "Good afternoon. Two posts are taking off, three are worth watching, and one became unavailable while you were away."

Then a prioritized attention queue (not a raw leaderboard), grouped by state:
- **Act now** — confirmed breakout / highly actionable momentum
- **Watch closely** — unusual growth, needs more evidence
- **New** — recently discovered, still establishing trajectory
- **Steady** — normal, lower on the page
- **Unavailable** — deleted/private, history preserved

The queue is NOT limited to posts that fired an official alert — momentum state drives it.

## Post Cards
Understandable in a few seconds. Show only what helps decide whether to open:
- creator name + avatar, short caption, publish time
- marketer-facing state (e.g. "Taking off")
- ONE meaningful performance statement ("Views grew 3.4× faster than this creator's usual posts over the last two hours")
- small trend sparkline, last-updated time, whole card clickable
Avoid dumping every raw metric. Don't constantly reorder rows with noisy animation — update calmly.

## Post Detail (the decision surface)
1. **Status + summary** — "Taking off. Sustained unusually fast growth across three checks, outperforming this creator's normal early trajectory."
2. **Evidence chart** — metric history over time, annotated (published, momentum rise, watch, breakout, latest). Inspectable, not decorative.
3. **Why this matters** — AI translates evidence into business meaning. It interprets, does NOT narrate visible numbers.
   - Good: "Momentum continued for three consecutive checks rather than a one-time spike, now growing faster than this creator's recent posts at similar age."
   - Bad: "Views are 18,420 and likes are 1,204."
4. **Suggested next action** — framed as considerations, never autonomous: "consider resharing while momentum is increasing," "check usage rights before promoting," "contact the creator while active." Do NOT fabricate contracts, budgets, or rights.
5. **History** — preserve prior states/alerts. If deleted: freeze live metrics, keep history, state last successful update.

## AI-Native Behavior
Deterministic code owns: metric math, velocity/acceleration, baselines, state classification, alert eligibility, dedup.
LLM owns: briefings, explanation, translating evidence to marketer language, suggested considerations.
The LLM must NOT control detection or alerts. The product must stay useful if the LLM is unavailable.

## Trust & Explainability
Every important claim answers: compared with what? over what window? based on which metrics? how fresh? how confident?
Prefer specific evidence ("Shares up 82% over the last hour, elevated across three checks") over vague AI ("this is resonating"). Never imply causation from engagement alone.

## Visual Direction
Feel: minimal, editorial, modern, lightly playful, calm under high info volume.
Use whitespace, strong typography, restrained motion, clear hierarchy, small personality.
Avoid: admin-dashboard templates, dense KPI grids, excessive gradients, neon "AI" styling, fake charts, constant animation, dozens of badges, developer terms, unexplained scores, arbitrary leaderboards.
A marketer should understand the first screen without onboarding.

## States (don't skip)
Design loading (skeletons, no layout jump), empty (explain what will appear), stale (warn without panic), error (no optimistic cover-ups), deleted (unavailable + preserved history). Human-readable timestamps, exact on hover.

## Product Decision Filter
Before adding anything, ask: does it help notice sooner? explain why it matters? reduce manual checking? support a real action? grounded in real data?
Final test: "Would this save meaningful time for someone managing 100 creators?" If mostly no, don't build it.

## Working Method
1. State the marketer decision the screen supports.
2. Inspect the actual API response + data model.
3. Separate facts vs derived signals vs AI explanation.
4. Smallest useful hierarchy.
5. Design loading/empty/stale/deleted/error before coding.
6. Core path before polish.
7. Scrub copy for technical language; verify claims against backend data.
8. Remove anything impressive that doesn't improve the decision.

## North Star
The reviewer should think: "This person didn't just visualize an API. They understood the marketer's job, built a reliable monitoring system, and turned it into a focused AI product with taste."