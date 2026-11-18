# Fact cards: Goals and 12 projects on the same 8 points

Snapshot: 2026-11-18 (UTC). Each project card comes from that project's README as saved by
`screen.py`. The Goals card comes from this repo's own files: `README.md`, `ROADMAP.md`,
`AGENTS.md`, `docs/architecture.md`, `docs/GOAL_EXECUTION_MEMORY.md`.

How these were made and checked:

- Helper agents read the files and wrote one card each. Every point carries a short quote and a location.
- `verify_quotes.py` looks up every quote of 4 words or more in the source text. Result: all 99 found word for word.
- Six high-impact cells were also checked by hand against the source. All six matched.
- **Not stated** means the README does not say. It does not mean the project lacks the feature.
- Re-check: `python3 verify_quotes.py cards.md README_CACHE_DIR GOALS_DIR`. Fill the cache with `screen.py`.

### Goals

1. **What it is.** Tool: a small CLI plus plugin that keeps an agent's plan, proof, and decisions in files.
   - Quote: "working over plain files in your own project"
   - Where: README.md, "How it works"
2. **How the loop runs.** Your agent's native `/goal` loop repeats the work. An opt-in Stop hook can end it.
   - Quote: "builds on the native `/goal` loop"
   - Where: README.md, opening paragraph and "Keep long runs safe"
3. **How it knows it is done.** Checks the tool runs itself, with recorded exit codes. The agent declares which checks; the engine runs them.
   - Quote: "Declare the verifications you want; the engine proves them."
   - Where: AGENTS.md, "Known constraints," bullet 2
4. **Where state lives.** Plain files in your repo, plus private memory in `~/.goals/user/`. No database. Survives `/clear` and new sessions (stated claim).
   - Quote: "survive a /clear or a brand-new session"
   - Where: README.md, "How it works"; docs/architecture.md, section 1
5. **Understanding first.** Yes. It asks about pain and desired feel, then waits for your yes. Hosts without the reply hook can close it, labelled "not verified."
   - Quote: "Phase one isn't coding — it's getting your goal right."
   - Where: README.md, "What Goals does"; ROADMAP.md, Discovery
6. **Decisions and history.** Each decision records its pick, reversibility and reason (stated claim). Audit trail: append-only event log. Preferences change only when you state or confirm them.
   - Quote: "already an append-only event log"
   - Where: ROADMAP.md, "Evidence ledger"; docs/GOAL_EXECUTION_MEMORY.md, "Two tiers"
7. **Stop limits.** Opt-in (`GOALS_ENFORCE=1`). Stops after 3 failed reviews per phase by default, or a token budget you set. Time limit: Not stated.
   - Quote: "hands control back to you when either guard trips"
   - Where: README.md, "Keep long runs safe"
8. **Agents, install, upkeep.** Agents: Claude Code and Codex. Install: plugin commands or `goals setup`. License: MIT. Maintenance: Not stated; issues and PRs welcome.
   - Quote: "your AI assistant (Claude Code, Codex, …)"
   - Where: README.md, "How it works," "Get started," "License"

**A. Limits the project admits to**

- **Faked yes possible.** Agent can fake a user reply; the files call that out of scope. "Deliberate forgery is out of scope" (ROADMAP.md, Known limitations)
- **Log is writable by the agent.** "can write every file, including the event log" (ROADMAP.md, Threat model)
- **Evidence not yet hard to fake.** Run capture and artifact hashes are planned. "make captured evidence stronger and harder to fake" (ROADMAP.md, Evidence ledger)
- **Codex hook unverified.** Payload field names are assumed, not checked. "are assumed to match Claude Code's and aren't verified" (ROADMAP.md, Known limitations)
- **Stop gate: opt-in, fails open.** If it breaks, it never blocks you. "fails open if anything goes wrong" (README.md, "Keep long runs safe")
- **No standalone run yet.** A native agent still owns the inner loop. "would let Goals drive a goal end to end on its own" (ROADMAP.md, Mode B standalone runner)

**B. Type:** tool

### cobusgreyling/loop-engineering

1. **What it is:** A pattern library for running agents around a codebase, plus an npm CLI. "This is a pattern library for operating agents around a codebase." (lines 32, 50)
2. **How the loop runs:** Each pattern runs on its own cadence, from 5–15 minutes up to daily. The thin loop runs in GitHub Actions. "Run a loop in GitHub Actions with almost no files" (line 56)
3. **How it knows it is done:** A verifier judges results; the README does not name the checks the tool runs. "only after the verifier has been right for a week" (line 86)
4. **Where state lives:** A `STATE.md` file. Whether it survives /clear or a new session is not stated. "Empty repo → first `STATE.md` walkthrough" (line 84)
5. **Understanding first:** Not stated.
6. **Decisions and history:** Recent runs weigh more than files in the Loop Ready score. No audit trail or preference memory is described. "Loop Ready now weights recent runs harder than files on disk." (line 88)
7. **Stop limits:** No round, token, or time cap is stated. A `cost` command exists. "npx @cobusgreyling/loop cost --pattern daily-triage --level L1" (line 81)
8. **Agents, install, upkeep:** Agents: Claude Code (default), Grok, Codex, OpenCode, OpenClaw. Installs via npx; MIT license. First response to docs and small PRs: within 48 hours. "--tool` defaults to `claude` if you omit it." (lines 36, 102, 129)

Type: guide

### valkor-ai/loom

1. **What it is:** An open delivery harness for coding agents (Claude Code, Codex, OpenCode) that runs software delivery as a stateful loop. "Loom is an open delivery harness for Claude Code, Codex, OpenCode, and other coding agents." (line 4)
2. **How the loop runs:** A local MCP server drives it: the agent submits each result, and Loom routes the next step, including repairs. "The agent does not decide the whole workflow from memory; it asks Loom for the next request" (line 272)
3. **How it knows it is done:** Loom keeps tests, runtime checks, previews, and review findings as verification evidence; it validates each submitted artifact. "Execute bounded tasks through the agent, then write a TaskResult with evidence." (lines 68, 278–279)
4. **Where state lives:** Project-local `.loom/` folder: requirements, tasks, results, repair history. A new session resumes from it; /clear is not mentioned. "A new session can pick up the actual state of the work" (line 56)
5. **Understanding first:** Yes, Loom clarifies and confirms scope before building. Waiting for an explicit yes is not stated. "Clarify and confirm scope, optionally using registered knowledge sources." (line 275)
6. **Decisions and history:** Confirmed requirements, decisions, and task boundaries are kept in `.loom/`, with repair history. Preference memory: not stated. "Confirmed requirements, decisions, and task boundaries" (line 66)
7. **Stop limits:** Not stated.
8. **Agents, install, upkeep:** Claude Code, Codex, OpenCode. Installs by curl script or PowerShell. Apache-2.0 license. Maintenance policy: not stated. "Run the same install command again to upgrade." (lines 149, 367)

Type: tool

### agentic-in/inferoa

1. **What it is:** A terminal agent harness (TUI and CLI) with a `/loop` command for long-horizon loops. "Inferoa is an Inference-native Tokenmaxxing Agent Harness for Loop Engineering" (line 25)
2. **How the loop runs:** The harness's own `/loop` command repeats inspect, edit, test, verify steps across loop tasks. The repeat mechanism is not described. "`/loop` runs durable recursive loops that inspect, edit," (line 32)
3. **How it knows it is done:** It uses tests, tool results, and completion evidence as feedback, and runs until the work is proven. "plans, tests, tool results, research metrics, and completion evidence" (lines 63–65)
4. **Where state lives:** Not stated.
5. **Understanding first:** `/plan` turns scope into a plan before execution. Waiting for a yes is not stated. "turns ambiguous scope into an inspectable plan before execution." (line 149)
6. **Decisions and history:** Loops keep attempts, verification evidence, and decisions active. Explanations of choices and preference memory: not stated. "loop tasks, attempts, verification evidence, and decisions active" (lines 147–148)
7. **Stop limits:** Finish condition: the loop runs until the work is proven. No round, budget, or time cap is stated. "Keep the engineering loop running until the work is proven" (line 82)
8. **Agents, install, upkeep:** Its own harness; Claude Code or Codex support not stated. Installs via npm (`inferoa@dev`). License not stated. "The `@dev` dist-tag tracks the latest build published from `main`." (lines 99, 102)

Type: tool

### ChaoYue0307/awesome-loop-engineering

1. **What it is:** A field guide linking 1022 sources to 22 operational patterns, 22 schema-checked contracts, and 8 runtime starters. "A practical field guide and implementation kit for recurring, stateful, verified AI-agent systems." (lines 8, 56)
2. **How the loop runs:** The kit describes a cycle that a trigger or cadence starts and that repeats. Its example is a dry run on one queue item. "Repeat, report, open a PR, or escalate to a human" (line 183)
3. **How it knows it is done:** The loop shape verifies with tests, evals, traces, or reviewers; worked paths name completion signals. Whether the kit runs these itself is not stated. "including commands and verifiable completion signals" (line 140)
4. **Where state lives:** Not stated.
5. **Understanding first:** Not stated.
6. **Decisions and history:** Not stated.
7. **Stop limits:** The kit says recurring work needs bounded budgets; no specific round, token, or time cap is stated. "recurring work also needs explicit triggers, verification, durable state, bounded budgets, and human handoff" (line 58)
8. **Agents, install, upkeep:** No agent named in lines 1–200. Install: clone the repo and run a Python dry run. License CC0-1.0. Current release v0.9.0. "clone the repository and inspect a bounded queue item without an agent account" (lines 25, 80, 142)

Type: catalog

Note: the awesome-loop-engineering card covers only lines 1 to 200 of its README, so Not stated there means not in those lines.

### snarktank/ralph
1. **What it is:** Bash loop that runs Amp or Claude Code until all PRD stories pass. "autonomous AI agent loop that runs AI coding tools" (L5)
2. **How the loop runs:** A bash script starts a fresh AI instance each iteration. "The bash loop that spawns fresh AI instances" (L136)
3. **How it knows it is done:** The agent's own word: it outputs a COMPLETE tag once every story passes. Typecheck and tests are listed as steps; how they run is not stated. "When all stories have `passes: true`" (L207)
4. **Where state lives:** prd.json, progress.txt, AGENTS.md, and git history, not the chat. Survival across /clear or a new session: inferred from files on disk (L5). "Memory persists via git history" (L5)
5. **Understanding first:** Asks clarifying questions while writing the PRD. No approval gate before the loop is described. "Answer the clarifying questions." (L98)
6. **Decisions and history:** progress.txt keeps append-only learnings, AGENTS.md gets patterns, and runs are archived by date. Decision reasons: Not stated. "Append-only learnings for future iterations" (L141; L187, L233)
7. **Stop limits:** Max iterations (default 10), or stop when every story passes. No budget or time cap stated. "Default is 10 iterations." (L120)
8. **Agents, install, upkeep:** Amp (default) or Claude Code; install by copying files or from the Claude Code marketplace. License and upkeep: Not stated. "One of the following AI coding tools installed and authenticated" (L13)

Type: tool

### anthropics/claude-plugins-official (plugins/ralph-loop)
1. **What it is:** Claude Code plugin that runs the Ralph technique through a Stop hook. "Implementation of the Ralph Wiggum technique" (L3)
2. **How the loop runs:** A Stop hook blocks Claude's exit and feeds the same prompt back inside the current session. "Stop hook feeds the SAME prompt back" (L23, L27)
3. **How it knows it is done:** The agent's own word: it must output the completion phrase, matched exactly. "uses exact string matching" (L134)
4. **Where state lives:** Files and git history in the project. Survival across /clear or a new session: Not stated. "Claude's previous work persists in files" (L31)
5. **Understanding first:** Not stated
6. **Decisions and history:** Git history is read each iteration. No log or decision record is described. "Each iteration sees modified files and git history" (L32)
7. **Stop limits:** `--max-iterations`, unlimited by default; the README says always set it. No budget or time cap stated. "Always use `--max-iterations` as a safety net" (L121; L60)
8. **Agents, install, upkeep:** Built for Claude Code; no other agent named. Windows needs Git for Windows. Install steps, license, and upkeep: Not stated. "AI development loops in Claude Code" (L3; L174)

Type: tool

### AnandChowdhary/continuous-claude
1. **What it is:** CLI that loops Claude Code or Codex, opening, checking, and merging a GitHub PR each run. "a CLI tool to run Claude Code in a loop" (L6)
2. **How the loop runs:** A Bash script repeats the agent: new branch, commit, PR, wait for checks, merge. "the Bash script acts as the conductor" (L23; L25-29)
3. **How it knows it is done:** The agent's word: a completion phrase, 3 in a row by default. The tool also waits for real PR checks before merging (L68). "If multiple agents decide that the project is complete" (L72; L201)
4. **Where state lives:** A notes file in the repo, plus git branches and PRs. Survival across /clear or a new session: inferred from the notes file on disk (L71). "maintains continuity by passing context between iterations" (L71)
5. **Understanding first:** Not stated
6. **Decisions and history:** The notes file is a handoff log. `--knowledge-file` keeps durable project knowledge. Failed PRs are closed, not kept. "a durable project knowledge file to maintain across iterations" (L192; L31)
7. **Stop limits:** Max runs, max USD, or max duration, whichever you set. Also stops after repeated errors. "Maximum number of iterations" (L181; L204)
8. **Agents, install, upkeep:** Claude Code or Codex CLI; curl installer; needs gh; GitHub-only PR automation; MIT license; has an update command. "An AI coding agent CLI" (L142; L150, L305, L365)

Type: tool

### tzachbon/smart-ralph
1. **What it is:** Spec-driven plugin for Claude Code and Codex. It writes spec files, then runs tasks one at a time. "Spec-driven development for Claude Code and Codex" (L13)
2. **How the loop runs:** A Stop hook inside the plugin keeps task execution going. Codex needs the hook trusted first. "moved execution into the plugin's Stop hook" (L238; L70)
3. **How it knows it is done:** Real checks: the spec-executor agent runs lint, type, and CI quality gates. Completed work is marked in tasks.md. "run lint, type, and CI checks" (L130, L137, L153)
4. **Where state lives:** Files in the spec folder (research, requirements, design, tasks, .progress.md). Can resume after a stopped session. /clear: Not stated. "can resume after a stopped session" (L27; L186-198)
5. **Understanding first:** Yes, it pauses for approval between spec phases unless `--quick` is used. Clarifying questions: Not stated. "approval checkpoints between spec phases outside quick mode" (L144; L84)
6. **Decisions and history:** .progress.md keeps decisions and learnings for later tasks. Spec files stay in the project for review. "recover decisions and learnings" (L200; L27)
7. **Stop limits:** No round, budget, or time cap stated. Manual stop: `/ralph-specum:cancel`. "Cancel execution and remove loop state" (L114)
8. **Agents, install, upkeep:** Claude Code and Codex; install via plugin marketplace commands; MIT license; PRs welcome; check GitHub releases for later changes. "for Claude Code and Codex" (L13; L55-67, L240, L244, L261)

Type: tool

### computerlovetech/ralphify
1. **What it is:** Python runtime that runs a RALPH.md loop directory through any agent CLI. "the runtime for loop engineering" (L17; L176)
2. **How the loop runs:** The ralph runtime repeats: run commands, fill the prompt, pipe it to the agent. Stops at Ctrl+C or after `-n` iterations. "loops until Ctrl+C" (L132-136)
3. **How it knows it is done:** No done check described. Commands such as tests run each iteration as feedback. "run before each iteration" (L110)
4. **Where state lives:** Git commits hold progress. RALPH.md is re-read from disk each iteration. /clear and new-session survival: Not stated. "Every iteration commits." (L166; L140)
5. **Understanding first:** Not stated
6. **Decisions and history:** Git log is the history. Rules are added to RALPH.md while it runs. No decision log described. "`git log` shows what happened" (L166; L140-146)
7. **Stop limits:** `-n` sets an iteration count; otherwise it runs until Ctrl+C. No token, budget, or time cap stated. "run 5 iterations then stop" (L133)
8. **Agents, install, upkeep:** Any agent CLI that takes piped input, such as Claude Code or Codex. Install: `uv tool install ralphify`. MIT license. "kept for educational purposes" (L13; L57, L177, L181)

Type: tool

### parcadei/Continuous-Claude-v3

1. **What it is:** Development environment that makes Claude Code a continuously learning, multi-agent system. "transforms Claude Code into a continuously learning system" (opening paragraph)
2. **How the loop runs:** Hooks mark each step of the Continuity Loop, and /clear starts fresh context with state kept. "Hooks intercept Claude Code at lifecycle points." (Hooks System)
3. **How it knows it's done:** Hooks run pyright and ruff after edits; the /fix chain has a test step. Done rule not stated. "kraken → test → commit" (Workflows, /fix)
4. **Where state lives:** Files in thoughts/ (ledgers, handoffs); memory in PostgreSQL. Handoffs carry state to new sessions. Survives /clear per the loop diagram. "Fresh context + state preserved" (The Continuity Loop (Detailed))
5. **Understanding first:** /build greenfield starts with a discovery interview. Waiting for your yes before building: not stated. "to get an interactive question flow" (Meta-Skill Reference)
6. **Decisions and history:** A daemon turns session thinking blocks into stored learnings; ledgers and handoffs hold session state. "thinking blocks contain the real reasoning" (Memory System)
7. **Stop limits:** No round, budget or time cap stated; /premortem blocks on HIGH-severity risks until you accept or mitigate them. "Blocks on HIGH severity until user accepts" (Workflows, /premortem)
8. **Agents, install, upkeep:** Claude Code only; no other agent named. Setup wizard installs it; an update command syncs it. MIT license. "Claude Code CLI" (Quick Start, Prerequisites)

Type: tool

### AMAP-ML/LoopArena

1. **What it is:** Benchmark that scores models as runtime Controllers guiding a separate coding Worker. "evaluates models as runtime Controllers" (opening paragraph)
2. **How the loop runs:** The Worker changes the repo; a read-only Reporter summarizes progress, and the Controller returns the next Loop Contract. "returns the next Loop Contract" (Benchmark)
3. **How it knows it's done:** The Controller decides when to stop; coding tasks use each source's own terminal evaluation. "use source-native terminal evaluation" (Benchmark)
4. **Where state lives:** Run output goes to a JSONL file. Survival across /clear or a new session: not stated. "--output runs/type1-smoke.jsonl" (Quick start)
5. **Understanding first:** Not stated
6. **Decisions and history:** A protocol doc covers roles, budgets and scoring; a dated News list records updates. No user-preference memory stated. "for role boundaries, budgets, and scoring" (Benchmark)
7. **Stop limits:** Controller comparisons use one shared budget; the Controller decides when to stop; numeric caps not stated. "with a shared Worker, Reporter, task, budget" (opening paragraph)
8. **Agents, install, upkeep:** No coding agent named; needs an OpenAI-compatible endpoint. Installs via pip. Apache-2.0. News lists updates; no maintenance policy stated. "Configure an OpenAI-compatible endpoint" (Quick start)

Type: benchmark

### HKUDS/DeepCode

1. **What it is:** Open-source coding agent with TUI, Desktop and Web clients on one local service. "an open-source Coding Agent for real software engineering" (What Deep means in DeepCode)
2. **How the loop runs:** Goals run in turns; a claim that falls short goes back to the agent. "goes back to the agent with what is missing" (What Deep means in DeepCode)
3. **How it knows it's done:** DeepCode runs the confirmed checklist commands itself; an optional independent reviewer checks each requirement. "runs the checklist you confirmed itself" (What Deep means in DeepCode)
4. **Where state lives:** Settings, sessions and logs sit in ~/.deepcode; a local service keeps Goals across restarts. Survival through /clear: not stated. "survives a restart or a closed window" (What Deep means in DeepCode)
5. **Understanding first:** No discovery interview stated. Goal checklists need your confirmation; Ask mode asks before edits and commands. "Ask asks before edits and commands" (Security and data)
6. **Decisions and history:** Edits show as diffs, Goals keep tool calls and checks, and project notes sit in .deepcode/memory/. "keeps its tool calls and checks" (Why DeepCode)
7. **Stop limits:** Goals can have a time limit or token budget, and stop when stuck or repeating. Max rounds not stated. "stops when it is stuck" (What's new)
8. **Agents, install, upkeep:** Its own agent; no Claude Code or Codex named; reads AGENTS.md and CLAUDE.md. Installs with uv; MIT license. "uv tool install --python 3.12 deepcode-hku" (Quick start)

Type: platform
