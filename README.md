# Goals

**A no-nonsense goal workflow engine.** It keeps your AI on a plan you can read,
decide on, and trust.

**Just say what you want — for example:**

- *"build me a weight-loss tracking app"*
- *"make a web app that resizes and tags my photos"*
- *"add login and payments to my site"*
- *"clean up and document this messy codebase"*

## What Goals does

- **Breaks a big goal into clear steps.** Whatever you ask for, Goals splits it into
  ordered steps, each with a plain "done" line — so a big ask never turns into a mess.
- **Talks in plain words, not jargon.** Status, decisions, and "what needs you" are
  written for a person — no codes, no wall of technical output.
- **Shows proof, doesn't guess.** Every step has to show what was checked and what
  changed, so *done* really means done.
- **Lets you shape how it works.** Build the workflow once, check it for gaps, and
  improve it as you learn what works.

## Who it's for

Anyone using AI to get real work done:

- **If you don't code** — you describe the goal and approve decisions in plain English;
  your AI assistant does the heavy lifting, and Goals keeps it on track.
- **If you do code** — a durable, scriptable workflow layer that keeps long AI tasks on
  the rails, with evidence, gates, and a readable audit trail.

## How it works

```
   you say the goal
         │
         ▼
   Goals breaks it into clear steps  ──▶   your AI does the next step
         ▲                                        │
         │            you say yes   ◀──── plain decision + proof it works
         └─────────  repeat until done — with a record of everything  ◀─┘
```

Goals runs the **workflow**; your AI assistant (Claude Code, Codex, …) does the **work**.
Goals is the part that keeps it organized, legible, and accountable.

## Get started

**1. Install Goals** — one line. It installs everything it needs (including `uv` and
Python); nothing required up front.

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/ShivamGupta42/goals/main/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/ShivamGupta42/goals/main/install.ps1 | iex
```

**2. Connect your AI assistant** — one command, for Claude Code *and* Codex:

```bash
goals setup --agent both        # or: --agent claude  |  --agent codex
```

That's it. Now just talk to it in Claude Code:

| You type | What happens |
| --- | --- |
| `/goals:create "build me a weight-loss tracking app"` | Goals turns it into a tracked plan and starts step 1 |
| `/goals:next` | Do the next step; Goals saves the proof and checks it off |
| `/goals:check` | See where things stand and what (if anything) needs *you* |

Prefer the terminal? Use `goals start "…"`, then `goals next` and `goals check` — see
[The command set](#the-command-set).

<details><summary>Rather not pipe a script? Install manually</summary>

```bash
# needs uv (https://astral.sh/uv): curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install git+https://github.com/ShivamGupta42/goals.git
goals setup --agent both
```
</details>

## Why Goals exists

AI agents wander. They skip steps, make quiet decisions, and after a while you've lost
track of what they did. When they *do* turn to you to decide, it's hard — the choice
comes wrapped in jargon you shouldn't have to decode. And once it's built, they often
can't clearly tell you what they made or how.

Goals fixes that. Tell it what you want in plain English. It breaks that into a clear
plan, keeps your AI on track step by step, puts every decision to you in plain words
you can actually answer, and won't say "done" until there's proof. Works whether you
write code or not.

## The command set

Most people only need these:

| Command | What it does |
| --- | --- |
| `goals start "add login and payments to my site"` | Turn a goal into a tracked plan and open a workspace for it |
| `goals next` | Get the next step, ready to hand to your AI |
| `goals check` | Plain-language status: progress, proof, and what needs you |
| `goals view` | Open the dashboard — your goal at a glance, for humans |
| `goals loop` | Design, check, and improve the workflow itself |

## For developers

Under the hood, Goals is a small CLI + Claude Code / Codex plugin. It keeps goal state,
evidence, decisions, and an append-only history as plain files in your repo, plus a
portable spec any agent can pick up. On `main` it works in an isolated git worktree so
your checkout stays clean. `goals check --json` gives agents a machine-readable view.

Note: `goals start` runs in a git project (it makes a safe, isolated copy to work in).
Full CLI, portability commands, and the visual loop builder are documented in
[docs/](docs/) and `goals --help`.

## Contributing

Issues and PRs welcome.

## License

[MIT](LICENSE)
