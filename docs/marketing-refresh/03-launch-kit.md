# Refreshed launch kit — open-source promotion

**Phase P3 deliverable (part 2).** Copy + checklist for promoting Goals as an OSS
project, refreshed to include the five features the `marketing` branch omits
(executed-proof gates, PACERS building journey, skill-first architecture, Trust V1
capability gaps, typed gate findings). Positioning is unchanged: **a no-nonsense
goal workflow engine.** Every `goals ...` command below is real (`goals --help`).

---

## A. One-liners (use everywhere, identically)

- **Goals** — a no-nonsense goal workflow engine. Keeps your AI on a plan you can
  read, decide on, and trust.
- Your AI wanders and makes decisions you can't follow. Goals keeps it on a plan
  you can read — and **proves each step ran** before it counts as done.
- Tell your AI what you want in plain English. Goals turns it into tracked steps,
  records the decisions, and won't check a step off until its checks actually pass.

## B. Feature bullets (the "what you get" table)

| You get | Why it's different | Backed by |
| --- | --- | --- |
| **Plain-English goals → tracked phases** | No DSL, no config; just say what you want | `goals start` / `/goals:create` |
| **Executed-proof "done"** | A phase passes only when its checks *run* and exit 0 — the agent can't assert success | `gates.py` |
| **A readable building journey** | The dashboard shows *why* the agent did things and which assumptions it leaned on (PACERS) | `journey.py`, `goals assess` |
| **Skill-first** | Discovers and uses your agent's skills live from `SKILL.md`; ships its own bundled | `skill_discovery.py`, `skills/` |
| **Knows what it can't do** | Checks it has the skills/tools a goal needs *before* working, and names the gaps | `goals capability check` (Trust V1) |
| **Durable + portable** | Goal, decisions, and evidence live in files you own; survives `/clear`, new sessions, agent switches | `.goals/`, `goals export` |
| **Vendor-neutral** | Works with Claude Code *and* Codex via one setup | `goals setup --agent both` |
| **Human dashboard** | A page a non-technical stakeholder can actually read | `goals view` |

## C. README first screen (demo-first, drop-in opener)

```md
# Goals

**A no-nonsense goal workflow engine.** Keeps your AI on a plan you can read,
decide on, and trust — and proves each step ran before it counts as done.

![hero demo](docs/marketing/assets/goals-demo-color.gif)   <!-- re-record: see follow-ups -->

## Quickstart (30 seconds)
\`\`\`bash
curl -fsSL https://raw.githubusercontent.com/ShivamGupta42/goals/main/install.sh | sh
goals setup --agent both
\`\`\`
Then in Claude Code: `/goals:create "build me a weight-loss tracking app"`

## How it works
[architecture diagram #2 — the goal lifecycle]   <!-- docs/marketing-refresh/assets/architecture-2.svg -->
```

> Reorders the existing README to quickstart-first (per `06-readme-draft.md`) and
> adds the lifecycle diagram + the executed-proof claim. Keep the existing
> "Who it's for", "Command set", and "For developers" sections below the fold.

## D. Show HN (refreshed)

**Title:** `Show HN: Goals – keep your AI agent on a plan you can read, and prove each step ran`

**Body:**
> AI coding agents wander, make quiet decisions you can't follow, and will happily
> tell you a step is "done" when it isn't. Goals is a small CLI + Claude Code/Codex
> plugin that fixes that without taking over the agent.
>
> You say the goal in plain English. Goals breaks it into phases, records the
> assumptions and decisions as a readable "building journey", and — the part I care
> about most — a phase only counts as done when its checks **actually execute and
> exit 0**. The agent can't assert success; it has to earn it.
>
> Everything lives as plain files in your repo, so the goal survives `/clear`, a new
> session, or switching agents. It also checks it *has* the skills a goal needs
> before starting, instead of failing halfway.
>
> Honest line: Goals runs the workflow; your agent does the work.
>
> Repo + 30-second install: <link>

## E. Reddit (problem-led; link last; one post/community/week)

- **r/ClaudeAI** — "I made my agent's plan (and its proof) survive `/clear`."
- **r/ChatGPTCoding** — "A vendor-neutral goal+evidence layer that won't mark a
  step done until the checks actually run."
- **r/LocalLLaMA** — "Durable goal state for any agent via a plain CLI — no vendor
  lock-in."

Lead with the pain, show the GIF, link last. Keep self-promo <10% of activity.

## F. X / build-in-public thread (refreshed beats)

1. The pain: your agent forgets the plan on `/clear` and says "done" when it isn't.
2. The fix: plain-English goal → tracked phases, in files you own.
3. The twist: a step only passes when its checks *run* (show the verify output).
4. The trust bit: it tells you which skills it's missing before it starts.
5. CTA: 30-second install, works with Claude Code + Codex.

## G. Honesty guardrails (don't undercut trust)

- Lead with users who can act **today** (Claude Code / Codex). Don't headline
  "for non-technical people" until onboarding needs no terminal.
- Say "keeps your AI on a plan," never "the AI runs autonomously."
- Never claim a feature the code doesn't have — `tests/test_skill_hygiene.py`
  enforces honest CLI examples; apply the same bar to claims.

---

## H. OSS launch checklist (sequenced, lowest-risk → highest-variance)

**Phase A — Foundation (do first, no audience needed)**
- [ ] README is demo-first (hero GIF + lifecycle diagram above the fold).
- [ ] Architecture diagrams merged (`02-architecture-diagrams.md`, 4 SVGs rendered).
- [ ] 30-second quickstart verified on a clean machine.
- [ ] GitHub About = the one-liner; topics: `claude-code`, `codex`, `ai-agents`,
      `agentic-coding`, `developer-tools`, `mcp`.
- [ ] Social-preview image set (use rendered `architecture-2.svg` → PNG, or hero GIF frame).

**Phase B — Compounding discovery (passive)**
- [ ] PRs into `awesome-claude-code` lists (jmanhype, ComposioHQ, GiladShoham) — see `07-awesome-list-and-marketplace.md`.
- [ ] Submit to plugin-marketplace directories (claudemarketplaces.com, ihistand/marketplace) — Goals already ships as a marketplace.
- [ ] PR into `awesome-ai-coding-tools`; list on LibHunt for SEO.

**Phase C — High-variance single shots (after A+B warm it up)**
- [ ] Show HN (only after the hero demo exists and install is clean-machine tested).
- [ ] Reddit posts (one problem-led post per community per week).
- [ ] X launch thread + ongoing build-in-public.
- [ ] (Optional, lower intent) Product Hunt / dev newsletters as a single push.

---

## I. Out of scope — follow-ups (need screen capture / live env)

These can't be produced headlessly; flagged, not silently dropped:

1. **Re-record the hero GIF** against current behaviour. The `marketing` branch
   `assets/goals-readme.tape` 5-beat shot list (start → check → `/clear` → resume)
   should gain a beat that shows `goals phase verify` running real checks and a
   beat on the building-journey dashboard. Re-render with VHS:
   `vhs docs/marketing/assets/goals-readme.tape`.
2. **Re-shoot the dashboard hero screenshot** (`dashboard-hero.png`) — it predates
   the PACERS building-journey reframe (#18). Run `goals view` on a real goal.
3. **Convert a rendered SVG to PNG** for the GitHub social preview (needs an
   image tool, e.g. `rsvg-convert` / `sharp`).
4. **Actually submit** the awesome-list PRs and post to HN/Reddit/X — owner action,
   gated on per-channel approval (`goals permission check`).
