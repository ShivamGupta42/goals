# Goals Workflow Improvements From Real-World Simulations

This note captures lessons from dogfooding Goals on small, real-world product
surfaces such as static landing pages. The important distinction: Goals already
helps prevent fake completion, but it can still accept weak outcomes when the
chosen acceptance criteria are too shallow.

## What Worked

- Phase review requires executed evidence, not prose-only claims.
- `goals phase verify` runs the declared automated checks in the goal worktree.
- `goals loop check` catches structural loop design gaps such as missing
  evidence requirements.
- Bundled skills can be installed into a disposable agent home and referenced
  from loop phases.

## Improvement List

1. Make runtime state the single source of truth.
   Every `phase accept`, `goals check`, and `goals view` should refresh
   `.goals/GOAL.md` and `.goals/goal-state.json`, so committed portable state
   cannot drift from `.agent-workflow` runtime state.

2. Let designed loops become the actual runtime phase plan.
   Add a `goals start --loop <file>` or `goals loop activate` path so a
   domain-specific `.loop` design is not merely a side artifact beside the
   default four-phase workflow.

3. Require criterion-to-verification mapping.
   A phase should pass only when each acceptance criterion is covered by a named
   verification, not merely because one automated command passed.

4. Add skill-provided validation profiles.
   Skill-first workflows should contribute done criteria and checks. For
   frontend landing pages, a skill profile should require browser screenshots,
   desktop and mobile smoke tests, overflow checks, CTA behavior, accessibility
   checks, reduced-motion handling, and proof/claim review.

5. Improve evidence projection.
   Evidence files may start with `ran: false` before verification; after
   runtime verification, the committed portable projection should show the
   executed results that reviewers and future agents need.

6. Add a real closeout command.
   `goals finish` should run `goals check`, `goals loop check`, export portable
   state, emit the dashboard, verify clean git state, summarize remaining risks,
   and recommend the next repository action.

7. Fix complete-goal guidance.
   When a goal is complete, `goals check` should not suggest moving to the next
   phase. It should suggest closeout/export/commit/archive actions.

8. Treat manual UX review as first-class evidence.
   The workflow should distinguish "static content exists" from "the target user
   can understand, trust, and act." Product-facing goals need JTBD, proof, and
   conversion-quality checks as explicit validation.

## Product-Surface Quality Bar

For landing pages and other user-facing product surfaces, the default done
criteria should include:

- The first viewport communicates product name, audience, value proposition, and
  primary action.
- A browser-rendered screenshot is inspected at desktop and mobile widths.
- No horizontal overflow, clipped primary content, unreadable text, or inert
  primary controls remain.
- Claims, metrics, testimonials, and proof elements are either sourced or framed
  as illustrative/demo content.
- The primary CTA has a real behavior or an explicitly documented demo behavior.
- Reduced-motion and accessibility basics are checked when motion or navigation
  affordances are present.

## Core Lesson

Goals is strongest at stopping fake progress. The next architectural step is
stopping technically verified but product-weak progress by making the quality of
the verification itself visible, reviewable, and skill-driven.
