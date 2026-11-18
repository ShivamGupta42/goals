# Goals compared with 12 open-source loop-engineering projects

Snapshot: 2026-11-18 (UTC). Evidence level: what each project's README says about itself.
Nothing was run. Facts and quotes are in [cards.md](cards.md); the project list and screen are in
[candidates.md](candidates.md).

## The short answer

1. **Goals is a workflow layer, not a loop runner.** It rides the agent's own `/goal` loop. At least 8 of the 12 projects run the loop themselves (shell script, stop hook, harness or their own agent).
2. **On proof, Goals sits with the better half.** 3 of the 5 Ralph-style tools stop when the agent says it is done (continuous-claude also waits on real PR checks). Goals, smart-ralph, Loom and DeepCode run checks themselves.
3. **No peer covers all three of Goals' ideas as fully as its README states them.** Those ideas are: ask first and wait for a yes, the tool runs the proof, and decisions and preferences are kept. DeepCode, Loom and smart-ralph each cover part of all three.
4. **Goals is weaker on hard stops, reach and visibility.** Its stop limits are opt-in, it works with 2 agents, and it has 17 stars.
5. **Best ideas to borrow:** limits switched on by default (continuous-claude), an independent reviewer and stuck detection (DeepCode), and a tool-led next step (Loom).

## The table

Short cells. "NS" = the README does not say. Full quotes and locations are in `cards.md`.

| Project | Type | Who drives the loop | How "done" is decided | Where state lives | Asks first? | Decisions and history | Stop limits | Agents, license |
|---|---|---|---|---|---|---|---|---|
| **Goals** | CLI + plugin | Agent's own `/goal` loop; opt-in stop hook | Engine runs declared checks, records exit codes | Plain files in repo; private memory; survives `/clear` (stated) | Yes: pain and feel first, waits for your yes | Pick, reversibility, reason; event log; preferences only on your say-so | Opt-in: 3 failed reviews per phase, token budget; time limit NS | Claude Code, Codex; MIT |
| [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering) | Pattern guide + npm CLI | Patterns on a cadence (5 min to daily), GitHub Actions | A verifier; checks not named | `STATE.md`; survival NS | NS | No audit trail described | A `cost` command; no caps | Claude Code (default), Grok, Codex, OpenCode, OpenClaw; MIT |
| [valkor-ai/loom](https://github.com/valkor-ai/loom) | Delivery harness | Local MCP state machine hands out each next step, incl. repairs | Verification evidence (tests, checks); validates artifacts | `.loom/` folder; new session resumes | Clarifies and confirms scope; explicit yes NS | Requirements, decisions, repair history kept; no preference memory | NS | Claude Code, Codex, OpenCode; Apache-2.0 |
| [agentic-in/inferoa](https://github.com/agentic-in/inferoa) | Terminal harness | Its `/loop` command | Tests, tool results, completion evidence | NS | `/plan` first; yes NS | Attempts, evidence, decisions kept in loop | Runs until proven; no caps | Own harness; npm; license NS |
| [ChaoYue0307/awesome-loop-engineering](https://github.com/ChaoYue0307/awesome-loop-engineering) | Catalog | A trigger or cadence starts each cycle | Tests, evals, reviewers (patterns, not run by the kit) | NS | NS | NS | Says to bound budgets; no caps | No agent named; CC0 |
| [snarktank/ralph](https://github.com/snarktank/ralph) | Bash loop | Bash script spawns a fresh agent each round | Agent's own COMPLETE tag once stories pass | `prd.json`, `progress.txt`, git | Clarifying questions while writing the PRD; no approval gate | Append-only learnings; reasons NS | Max iterations (default 10) | Amp or Claude Code; license NS |
| [anthropics ralph-loop plugin](https://github.com/anthropics/claude-plugins-official) | Claude Code plugin | Stop hook feeds the same prompt back | Agent's own phrase, exact match | Files and git; `/clear` NS | NS | Git history only | `--max-iterations`, off by default | Claude Code; Apache-2.0 (directory) |
| [AnandChowdhary/continuous-claude](https://github.com/AnandChowdhary/continuous-claude) | CLI | Bash script: branch, commit, PR, wait for checks, merge | Completion phrase, 3 in a row, plus real PR checks | Notes file, git branches, PRs | NS | Handoff notes, knowledge file | Max runs, max USD, max duration | Claude Code, Codex; MIT; GitHub only |
| [tzachbon/smart-ralph](https://github.com/tzachbon/smart-ralph) | Spec-driven plugin | Stop hook runs tasks one at a time | Real checks: lint, type, CI gates | Spec folder files; resumes after a stop | Approval between spec phases (not with `--quick`) | `.progress.md` decisions and learnings | No caps; manual cancel | Claude Code, Codex; MIT |
| [computerlovetech/ralphify](https://github.com/computerlovetech/ralphify) | Python runtime | Re-runs `RALPH.md` until Ctrl+C or `-n` | No done check; test commands feed back | Git commits; `RALPH.md` on disk | NS | Git log is the history | `-n` count | Any agent CLI; MIT; "educational", not maintained |
| [parcadei/Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3) | Claude Code environment | Hooks mark each step; `/clear` keeps state | Hooks run pyright and ruff; no done rule | `thoughts/` files plus PostgreSQL; survives `/clear` | `/build` starts with an interview; yes NS | A daemon stores learnings from sessions | No caps; `/premortem` blocks on high risk | Claude Code only; MIT |
| [AMAP-ML/LoopArena](https://github.com/AMAP-ML/LoopArena) | Benchmark | Controller sets the next contract; Worker edits | Controller decides; tasks use their own tests | JSONL run file; survival NS | NS | Protocol doc; no preference memory | Shared budget in comparisons; no numbers | No agent named; pip; Apache-2.0 |
| [HKUDS/DeepCode](https://github.com/HKUDS/DeepCode) | Coding agent (TUI, desktop, web) | Goals run in turns; short claims go back to the agent | Runs your confirmed checklist itself; optional independent reviewer | `~/.deepcode`; survives restart; `/clear` NS | No interview; you confirm the checklist; Ask mode | Diffs, tool calls and checks kept; project notes | Time limit or token budget; stops when stuck | Own agent; reads `AGENTS.md`, `CLAUDE.md`; MIT |

## Where Goals is stronger (by what the READMEs say)

1. **It starts from your pain and waits for a yes.** Goals asks about what hurts and how the result should feel, names what it does not understand, and waits for "yes, that's it" before building. The closest are smart-ralph (approval after each spec phase) and DeepCode (you confirm a checklist). Their READMEs do not mention starting from your pain points.
2. **The tool runs the proof.** "Declare the verifications you want; the engine proves them." The agent says which checks to run, the engine runs them and records the exit codes, so the agent's word alone does not close a step. Deliberate forgery is out of scope (see weaker point 4). Three of the five Ralph-style tools (snarktank/ralph, the official plugin, continuous-claude) stop on the agent's own completion phrase.
3. **Decisions are first-class.** Each one records the pick, whether it can be undone, and why. Preferences change only when you state or confirm them. No peer card mentions reversibility. Continuous-Claude-v3 goes the other way: a daemon turns session thinking into stored learnings.
4. **Plain files, no database.** Goals keeps plan, proof and decisions in files you can read and hand to another agent. Continuous-Claude-v3 adds PostgreSQL, and DeepCode keeps state in a local service.

## Where Goals is weaker

1. **Hard stops are opt-in and softer.** Goals' limits need `GOALS_ENFORCE=1`, cap at 3 failed reviews per phase or a token budget, do not state a time limit, and the gate "fails open". continuous-claude caps runs, money and time. DeepCode has a time limit, a token budget and stuck detection.
2. **It does not run the loop.** A native agent owns the inner loop; a standalone runner is only planned. At least 8 of the 12 peers drive their own.
3. **Narrow reach.** Claude Code and Codex only, and the Codex hook payload is "assumed", not verified. ralphify takes any agent CLI, Loom takes three agents, and cobusgreyling's toolkit lists five.
4. **Trust gaps it admits.** An agent can fake a user reply and can write the event log. No peer README discusses this, so we cannot say the peers do better. It is unknown, not a win for them.
5. **Small audience.** Goals has 17 stars and 5 forks. The peers range from 60 to 22,294 (the official plugin's 47,663 is the whole plugin directory). Six have 1,000 or more, not counting the official plugin.

## What to borrow

1. **Limits on by default, in three kinds.** Runs, money and time, as in continuous-claude (`--max-runs`, `--max-cost`, `--max-duration`). Fixes weakness 1.
2. **An independent reviewer and stuck detection.** DeepCode has an optional reviewer that checks each requirement, and it stops a goal that is stuck or repeating itself. Goals has review, but not these two.
3. **A tool-led next step.** Loom's agent asks for the next request and Loom validates and routes it. This is a way into Goals' planned standalone runner, and it fixes weakness 2.
4. **A readiness score and a cost command.** cobusgreyling's toolkit has a "Loop Ready" score and `cost`. Goals could answer "can this run unattended?" and "what did it cost?" in plain words.
5. **Suggested learnings from past sessions.** Continuous-Claude-v3 turns session thinking into stored learnings. Goals could offer them as suggestions and keep its rule that you confirm before they count.

## Known gaps

- **README level only.** No tool was run. A README states intent, not behavior.
- **Same team on both sides.** This was written by an agent working in the Goals repo for its owner. Goals went through the same card format and the same quote check as the others, but the conclusions are not independent.
- **Quote check proves the text exists, not that the reading is right.** All 99 quotes match their sources. Only 6 high-impact cells were checked by hand, so about 90 rely on the helper's reading.
- **One thin card.** The awesome-loop-engineering README is about 500 KB and only lines 1 to 200 were read, so its many "NS" cells mean "not in those lines".
- **The list is not the whole field.** Projects were found by the phrase "loop engineering" and by Ralph-style names. Agent frameworks that use neither were not searched. `conductor-oss/loop-engine` was left out for having no description.
- **A label was corrected.** `candidates.md` first called DeepCode the project least like a loop workflow. Its README describes confirmed checklists, checks it runs itself and a reviewer, so it is a close peer. The label was fixed.
- **Counts drift.** Stars and activity are from 2026-11-18 (UTC).
