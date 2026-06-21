# Refreshed launch kit — open-source promotion

**Phase P3 deliverable (part 2).** Copy + checklist for promoting Goals as an OSS
project, refreshed to include the five features the `marketing` branch omits
(executed-proof gates, PACERS building journey, skill-first architecture, Trust V1
capability gaps, typed gate findings). Positioning is now focused on
**long-running agent loops you can trust, verify, fix, and resume.** Every
`goals ...` command below is real (`goals --help`).

---

## A. One-liners (use everywhere, identically)

- **Goals** — a no-nonsense workflow engine for long-running agent loops you can
  trust, verify, fix, and resume.
- Agent loops run longer than your attention. Goals keeps the plan, decisions,
  and proof in files you own so the work stays verifiable.
- Tell your AI what you want in plain English. Goals tracks the loop, runs proof
  before done, and lets you resume without losing the thread.

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

**A no-nonsense workflow engine for long-running agent loops.** Goals keeps the
plan, decisions, and proof in files you own so you can trust, verify, fix, and
resume the work.

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

## F. LinkedIn + X / build-in-public

### LinkedIn post (loop-trust version)

```text
Loop engineering is becoming popular.

It feels like the next step in working with AI coding agents.

I've been running /loop in Claude Code on personal projects for months.

It is powerful. But the more loops I run, the more one thing stands out:

𝐀 𝐥𝐨𝐨𝐩 𝐧𝐞𝐞𝐝𝐬 𝐦𝐨𝐫𝐞 𝐭𝐡𝐚𝐧 𝐚 𝐩𝐫𝐨𝐦𝐩𝐭.

It needs a plan it can carry across sessions, a way to verify the work against your actual goal, and a record of what it decided while you were out of the loop.

That is what I am building with 𝐆𝐨𝐚𝐥𝐬.

𝐆𝐨𝐚𝐥𝐬 is a small CLI + plugin for Claude Code and Codex. It gives your agent a set of commands for creating the goal, getting the next step, checking status, viewing the dashboard, explaining decisions, and improving the loop itself.

Goals saves the work done in your loops in 𝐟𝐢𝐥𝐞𝐬 𝐲𝐨𝐮 𝐨𝐰𝐧: the goal, current phase, decisions, evidence, failed checks, and history.

Can we make agents run longer? We can.

The better question is: can we make longer runs something you can 𝐭𝐫𝐮𝐬𝐭, 𝐯𝐞𝐫𝐢𝐟𝐲, 𝐟𝐢𝐱, and 𝐜𝐨𝐧𝐭𝐢𝐧𝐮𝐞?

That is where Goals comes in:

- 𝐏𝐥𝐚𝐢𝐧-𝐄𝐧𝐠𝐥𝐢𝐬𝐡 𝐠𝐨𝐚𝐥𝐬: start from what you want and turn it into tracked phases.
- 𝐃𝐮𝐫𝐚𝐛𝐥𝐞 𝐬𝐭𝐚𝐭𝐞: keep the plan, decisions, evidence, failed checks, and history in readable files you own.
- 𝐕𝐞𝐫𝐢𝐟𝐢𝐞𝐝 𝐬𝐭𝐞𝐩𝐬: accept a step only after the proof actually runs.
- 𝐅𝐢𝐱𝐚𝐛𝐥𝐞 𝐟𝐚𝐢𝐥𝐮𝐫𝐞𝐬: use failed checks to point to the next repair instead of vague retrying.
- 𝐃𝐞𝐜𝐢𝐬𝐢𝐨𝐧 𝐞𝐱𝐩𝐥𝐚𝐢𝐧𝐞𝐫𝐬: explain technical choices in light of your goal, risk, and reversibility, not just specs.
- 𝐑𝐞𝐬𝐮𝐦𝐚𝐛𝐥𝐞 𝐰𝐨𝐫𝐤: continue after /clear, a new session, or switching between Claude Code and Codex.
- 𝐇𝐮𝐦𝐚𝐧 𝐯𝐢𝐞𝐰: open a readable dashboard with `goals view`.
- 𝐋𝐨𝐨𝐩 𝐢𝐦𝐩𝐫𝐨𝐯𝐞𝐦𝐞𝐧𝐭: use `goals loop` when the same issues keep repeating.

The project is open source:
https://github.com/ShivamGupta42/goals

If you are experimenting with long-running loops, try Goals on one real task and tell me where the workflow still feels hard to trust.

#LoopEngineering #AIAgents #ClaudeCode #OpenSource
```

### X / build-in-public thread (refreshed beats)

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

## I. Asset status

Done locally (in `docs/marketing-refresh/assets/`):

1. ✅ **Hero GIF re-recorded** against current behaviour — `goals-hero-opt.gif`
   (+ `.gif`, `.mp4`). New beats over the old marketing tape: a **building
   journey** beat (`goals assess journey`) and an **executed-proof** goal that
   survives `/clear`. Reproducible: `setup-demo.sh` + `goals-hero.tape`
   (`bash setup-demo.sh && cd … && vhs goals-hero.tape`).
2. ✅ **Dashboard hero screenshot** — `dashboard-hero.png`, captured from a real
   completed goal showing the PACERS building journey (#18). Reproduce with
   headless Chrome on any goal's `dashboard.html`.
3. ✅ **SVG → PNG social preview** — `architecture-1.png`, `architecture-2.png`
   (2× via `rsvg-convert`). Use `architecture-2.png` (the lifecycle) as the
   GitHub social-preview image.
4. ✅ **Loop-trust LinkedIn card** — `goals-linkedin-loop-trust.png`, rebuilt as a
   text-first deterministic Creative Production asset after the generated visual
   tested as decorative. Message: long-running loops you can trust, verify, fix,
   and resume. Footer includes the repo link.

Still owner actions (remote — can't be done locally):

5. **Push the branch / submit** the awesome-list PRs and post to HN/Reddit/X —
   gated on per-channel approval (`goals permission check`). Copy is ready above.
