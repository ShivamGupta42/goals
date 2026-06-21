# Goals — refreshed promotion kit (diagrams + marketing)

The single index that ties the architecture diagrams and refreshed marketing
together. Produced by the Goals-managed goal *"analyse the marketing branch +
create architecture diagrams + the marketing materials to promote Goals as OSS."*

**Why this exists alongside `docs/marketing/`:** the `marketing` branch is a
strong launch kit, but it was written before five architecture changes
(skill-first #22, Trust V1 #21, typed gates #20, executed-proof #19, PACERS
journey #18) and contains no architecture diagrams. This folder is the refreshed,
gap-filled layer. See `01-gap-analysis.md` for the exact deltas.

## Contents

| File | What it is |
| --- | --- |
| `00-definition-of-done.md` | The falsifiable goal definition + phase map |
| `01-gap-analysis.md` | `marketing` branch inventory vs. current code; risks; chosen approach |
| `02-architecture-diagrams.md` | 4 Mermaid diagrams (system, lifecycle, skill-first/Trust V1, portability) |
| `assets/architecture-1..4.svg` | The four diagrams rendered to static SVG |
| `03-launch-kit.md` | Refreshed one-liners, feature table, README opener, Show HN/Reddit/X copy, OSS checklist, follow-ups |

## What to keep from the existing `marketing/` branch

Feature-agnostic and still accurate — reuse as-is:
- `docs/marketing/01-distribution-research.md` — channel research
- `docs/marketing/02-goals-marketing-plan.md` — positioning + channel plan + metrics
- `docs/marketing/04-demo-production-guide.md` — demo method
- `docs/marketing/07-awesome-list-and-marketplace.md` — submission targets + status

## The four diagrams at a glance

1. **System architecture** — CLI + plugin + file-backed state + registries.
2. **Goal lifecycle** — start → assess (PACERS) → phase loop (evidence → verify →
   review → accept) → finish.
3. **Skill-first + capability-gap (Trust V1)** — checks it has the skills a goal
   needs before working.
4. **Portability layer** — why a goal outlives one session or one agent.

## The pitch, refreshed in one paragraph

Goals is a no-nonsense goal workflow engine: a small CLI + Claude Code/Codex
plugin that turns a plain-English goal into tracked phases, records the decisions
and assumptions as a readable building journey, and won't mark a phase done until
its checks **actually run and pass**. Everything lives as files in your repo, so
the goal survives `/clear`, a new session, or switching agents — and it tells you
which skills it's missing before it starts, instead of failing halfway.

## Assets (all rendered locally — see `03-launch-kit.md` §I)

- `assets/goals-hero-opt.gif` (+ `.gif`, `.mp4`) — re-recorded hero demo with
  building-journey + executed-proof beats; reproducible via `setup-demo.sh` +
  `goals-hero.tape`.
- `assets/dashboard-hero.png` — real completed-goal dashboard (PACERS journey).
- `assets/architecture-1..4.svg` + `architecture-1/2.png` — diagrams + social preview.

**Only remaining (remote, owner action):** push the branch, submit the awesome-list
PRs, and post to HN/Reddit/X — gated on per-channel approval (`goals permission check`).
