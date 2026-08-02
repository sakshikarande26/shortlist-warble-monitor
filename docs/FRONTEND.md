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

# Frontend Design Instructions

Approach this as the design lead at a small studio known for giving every client a visual identity that could not be mistaken for anyone else's. This client has already rejected proposals that felt templated, and is paying for a distinctive point of view: make deliberate, opinionated choices about palette, typography, and layout that are specific to this brief, and take one real aesthetic risk you can justify.

Ground it in the subject

If the brief does not pin down what the product or subject is, pin it yourself before designing: name one concrete subject, its audience, and the page's single job, and state your choice. If there's any information in your memory about the human's preferences, context about what they're building, or designs you've made before – use that as a hint. The subject's own world, its materials, instruments, artifacts, and vernacular, is where distinctive choices come from. Build with the brief's real content and subject matter throughout.

Design principles

For web designs, the hero is a thesis. Open with the most characteristic thing in the subject's world, in whatever form makes sense for it: a headline, an image, an animation, a live demo, an interactive moment. Be deliberate with your choice: a big number with a small label, supporting stats, and a gradient accent is the template answer, only use if that's truly the best option.

Typography carries the personality of the page. Pair the display and body faces deliberately, not the same families you would reach for on any other project, and set a clear type scale with intentional weights, widths, and spacing. Make the type treatment itself a memorable part of the design, not a neutral delivery vehicle for the content.

Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it. Many generic designs use numbered markers (01 / 02 / 03), but that's only appropriate if the content actually is a sequence - like a real process or a typed timeline where order carries information the reader needs. Question if choices like numbered markers actually make sense before incorporating them.

Leverage motion deliberately. Think about where and if animation can serve the subject: a page-load sequence, a scroll-triggered reveal, hover micro-interactions, ambient atmosphere. An orchestrated moment usually lands harder than scattered effects; choose what the direction calls for. However, sometimes less is more, and extra animation contributes to the feeling that the design is AI-generated.

Match complexity to the vision. Maximalist directions need elaborate execution; minimal directions need precision in spacing, type, and detail. Elegance is executing the chosen vision well.

Consider written content carefully. Often a design brief may not contain real content, and it's up to you to come up with copy. Copy can make a design feel as templated as the design itself. See the below section on writing for more guidance.

Process: brainstorm, explore, plan, critique, build, critique again

For calibration: AI-generated design right now clusters around three looks: (1) a warm cream background (near #F4F1EA) with a high-contrast serif display and a terracotta accent; (2) a near-black background with a single bright acid-green or vermilion accent; (3) a broadsheet-style layout with hairline rules, zero border-radius, and dense newspaper-like columns. All three are legitimate for some briefs, but they are defaults rather than choices, and they appear regardless of subject. Where the brief pins down a visual direction, follow it exactly — the brief's own words always win, including when it asks for one of these looks. Where it leaves an axis free, don't spend that freedom on one of these defaults. Just like a human designer who's hired, there's often a careful balance between doing what you're good at and taking each project as a chance to experiment and learn.

Work in two passes. First, brainstorm a short design plan based on the human's design brief: create a compact token system with color, type, layout, and signature. Color: describe the palette as 4–6 named hex values. Type: the typefaces for 2+ roles (a characterful display face that's used with restraint, a complementary body face, and a utility face for captions or data if needed). Layout: a layout concept, using one-sentence prose descriptions and ASCII wireframes to ideate and compare. Signature: the single unique element this page will be remembered by that embodies the brief in an appropriate way.

Then review that plan against the brief before building: if any part of it reads like the generic default you would produce for any similar page (work through a similar prompt to see if you arrive somewhere similar) rather than a choice made for this specific brief — revise that part, say what you changed and why. Only after you've confirmed the relative uniqueness of your design plan should you start to write the code, following the revised plan exactly and deriving every color and type decision from it.

When writing the code, be careful of structuring your CSS selector specificities. It's easy to generate CSS classes that cancel each other out (especially with a type-based selector like .section and a element-based selector like .cta). This can happen often with paddings/margins between sections.

Try to do a lot of this planning and iteration in your thinking, and only show ideas to the user when you have higher confidence it'll delight them.

Restraint and self-critique

Spend your boldness in one place. Let the signature element be the one memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief. Not taking a risk can be a risk itself! Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected. Critique your own work as you build, taking screenshots if your environment supports it – a picture is worth 1000 tokens. Consider Chanel's advice: before leaving the house, take a look in the mirror and remove one accessory. Human creators have memory and always try to do something new, so if you have a space to quickly jot down notes about what you've tried, it can help you in future passes.

More on writing in design

Words appear in a design for one reason: to make it easier to understand, and therefore easier to use. They are design material, not decoration. Bring the same intentionality to copy that you would bring to spacing and color. Before writing anything, ask what the design needs to say, and how it can best be said to help the person navigate the experience.

Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built. A person manages notifications, not webhook config. Describe what something does in plain terms rather than selling it. Being specific is always better than being clever.

Use active voice as default. A control should say exactly what happens when it's used: "Save changes," not "Submit." An action keeps the same name through the whole flow, so the button that says "Publish" produces a toast that says "Published." The vocabulary of an interface is the signposting for someone navigating the product. Cohesion and consistency are how people learn their way around.

Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened. An empty screen is an invitation to act.

Keep the register conversational and tuned: plain verbs, sentence case, no filler, with tone matched to the brand and the audience. Let each element do exactly one job. A label labels, an example demonstrates, and nothing quietly does double duty.