# Definition of Done — Marketing refresh + architecture diagrams

**Goal (plain English):** Analyse the local `marketing` branch and, given the
recent architecture changes, create architecture diagrams that explain how the
Goals repo works, plus the marketing materials needed to promote Goals as an
open-source project.

## Why this is not "just merge the marketing branch"

The `marketing` branch is a strong, mostly-complete launch kit (distribution
research, marketing plan, launch copy, one-line installers, demo GIFs). But it
was authored **before** five architecture changes that are now on the main line:

| Change | PR | Marketing impact |
| --- | --- | --- |
| Skill-first architecture | #22 | Goals now discovers/uses agent skills live; the "how it works" story changed |
| Trust V1 — capability-gap management | #21 | New, demoable trust feature absent from the copy |
| Typed gate findings (kernel facts + verdict rubric) | #20 | Strengthens the "evidence-based done" claim |
| Executed-proof gates | #19 | Core differentiator: a pass is *earned*, not asserted |
| PACERS building journey | #18 | The dashboard now shows a readable reasoning trace — a headline selling point |

And it contains **zero architecture diagrams**, which the user explicitly asked for.

## Definition of done (falsifiable)

This goal is done when all three hold:

1. **Gap analysis exists.** A written report inventories every `marketing` branch
   asset and classifies each headline claim as *accurate / stale / missing*
   against the current code, with the specific edits and the diagrams that don't
   yet exist. → `docs/marketing-refresh/01-gap-analysis.md`

2. **Architecture diagrams exist and match the code.** At least four diagrams,
   each node/edge traceable to a real module/command/registry in `src/goals`,
   `commands/`, or `registries/`:
   - System architecture (CLI + plugin + file-backed state + portability + registries)
   - Goal lifecycle (start → assess/PACERS → phase loop: evidence → verify → review → accept → finish)
   - Skill-first discovery + capability-gap flow
   - Executed-proof gate flow (why a pass is earned, not asserted)
   → `docs/marketing-refresh/02-architecture-diagrams.md` (Mermaid) + at least one rendered image.

3. **Refreshed, complete launch kit exists.** Updated README/launch copy and
   one-liners that include skill-first, Trust V1, executed-proof, and the readable
   building journey; an OSS launch checklist (repo metadata, awesome-lists,
   marketplaces, Show HN / Reddit / X copy); and a single index tying diagrams +
   copy + distribution plan together. Any asset that needs screen capture (hero
   GIF re-record) is explicitly flagged as a follow-up, not silently omitted.
   → `docs/marketing-refresh/03-launch-kit.md` + `docs/marketing-refresh/README.md`

## Phase map (from the recorded breakdown BD-81129d57)

- **P1 — Confirm outcome and plan** *(this phase)*: lock the definition of done above.
- **P2 — Gap analysis**: marketing branch inventory vs. current architecture.
- **P3 — Architecture diagrams**: the four diagrams, validated against code.
- **P4 — Refreshed launch kit**: copy + checklist + index.

## Out of scope (flagged, not done here)

- Re-recording demo GIFs / terminal captures (needs screen-capture tooling).
- Actually submitting PRs to awesome-lists / posting to HN/Reddit/X (owner action).
- Changing the locked positioning ("a no-nonsense goal workflow engine").
