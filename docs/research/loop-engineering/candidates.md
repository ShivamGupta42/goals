# Loop engineering on GitHub: candidates to compare with Goals

Snapshot: 2026-11-18 (UTC). Numbers come straight from the GitHub API (`candidates.json`).
Working definition used to pick projects: **tools that keep an AI coding agent in repeated
plan, act, check cycles until a goal is done.**

## The 12 candidates

| # | Project | Group | Stars | License | Last push | What it says it is |
|---|---|---|---|---|---|---|
| 1 | [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering) | named framework | 11,805 | MIT | 2026-11-18 | Patterns, starters and CLI tools (`loop-audit`, `loop-init`, `loop-cost`) for loop engineering with AI coding agents |
| 2 | [valkor-ai/loom](https://github.com/valkor-ai/loom) | named framework | 1,546 | Apache-2.0 | 2026-11-10 | Open delivery harness for Claude Code, Codex and OpenCode (Rust runtime) |
| 3 | [agentic-in/inferoa](https://github.com/agentic-in/inferoa) | named framework | 571 | Apache-2.0 | 2026-06-18 | Agent harness for loop engineering. Quiet for about 5 months |
| 4 | [ChaoYue0307/awesome-loop-engineering](https://github.com/ChaoYue0307/awesome-loop-engineering) | named framework (catalog) | 60 | CC0-1.0 | 2026-11-17 | Catalog of loop patterns and "loop contracts" with runtime starters |
| 5 | [snarktank/ralph](https://github.com/snarktank/ralph) | Ralph-style runner | 22,294 | MIT | 2026-02-02 | Agent loop that runs repeatedly until all PRD items are complete |
| 6 | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) (`plugins/ralph-loop`) | Ralph-style runner | 47,664 (whole plugin directory) | Apache-2.0 | 2026-11-18 | The official Ralph loop plugin for Claude Code |
| 7 | [AnandChowdhary/continuous-claude](https://github.com/AnandChowdhary/continuous-claude) | Ralph-style runner | 1,389 | MIT | 2026-10-29 | Ralph loop with pull requests: loops, waits for checks, merges |
| 8 | [tzachbon/smart-ralph](https://github.com/tzachbon/smart-ralph) | Ralph-style runner | 566 | MIT | 2026-10-28 | Spec-driven Ralph loop plugin with smart compaction |
| 9 | [computerlovetech/ralphify](https://github.com/computerlovetech/ralphify) | Ralph-style runner | 70 | MIT | 2026-08-12 | Educational loop runtime. Its description says "Not actively maintained" |
| 10 | [parcadei/Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3) | state and handoff | 3,952 | MIT | 2026-11-16 | Context management for Claude Code: hooks keep state in ledgers and handoffs |
| 11 | [AMAP-ML/LoopArena](https://github.com/AMAP-ML/LoopArena) | measurement | 156 | Apache-2.0 | 2026-10-15 | Benchmark that scores models as the controller of a loop |
| 12 | [HKUDS/DeepCode](https://github.com/HKUDS/DeepCode) | agentic platform | 16,851 | MIT | 2026-11-17 | Open coding agent with goals, a confirmed checklist it runs itself, and an optional reviewer. Tags itself "loop engineering" |

Rows 10 and 11 are **adjacent**: they share part of the problem (state handoff, measurement)
but are not loop workflows. Row 12 (DeepCode) was first labeled adjacent too. Its README
describes goals run in turns, checks it runs itself and a reviewer, so the comparison treats it
as a close peer. All three stay in so Goals is compared across the whole space.

## Not selected, and why

- `conductor-oss/loop-engine`: 0 stars, no description, no license. Nothing to compare yet.
- Guides and courses, not tools: `alchaincyf/loop-engineering-orange-book`,
  `cocodedk/loop-engineering`, `FareedKhan-dev/agentic-loop-engineering-course`,
  `invincible04/awesome-loop-engineering`, `ayeshakhalid13/LoopEngineering-CrashCourse`,
  `lamhotsiagian/loop-engineering`. Useful reading, but no workflow to run.
- `ghuntley/how-to-ralph-wiggum`: the write-up where the Ralph technique started (1,776
  stars, no license). Cited as background, not compared as a tool.
- Name matches in other fields: `dsta022/Loop-Engineering-for-VLA` (robot datasets),
  `erduo1998-cell/erduo-broll-loop-engineering` (video b-roll).

## How the 12 were screened

Rule: not archived, pushed within 365 days, README has at least 3 loop words
(loop, cycle, iterate, repair, retry, recursive, repeat) and at least 1 check word
(test, verify, check, review, criteria, validate, lint).

All 12 pass. One correction is logged: the first pass counted only the word "loop", and
`valkor-ai/loom` scored 2. Reading its README (lines 52 to 54) shows a real loop: clarify,
plan, build, run checks, repair failures, check again. The word list was widened and the
screen re-run, so Loom stays in.

## Files and commands used

- `docs/research/loop-engineering/candidates.json`: the snapshot (stars, license, last push, screen counts). Key `subject` holds Goals' own stats for scale: 17 stars, 5 forks, MIT, last push 2026-11-18.
- `docs/research/loop-engineering/screen.py`: re-runs the screen. `python3 -I screen.py OUT.json README_CACHE_DIR` (needs the `gh` CLI, logged in).
- `gh search repos "loop engineering"`, `"ralph wiggum loop"`, `"continuous claude"`, `"ralphify"`: how the candidates were found.
- `gh api repos/OWNER/REPO` and `gh api repos/OWNER/REPO/readme`: stats and README text.

## Comparison columns (used in the next phase)

Each project, and Goals itself, is described on the same 8 points, using only what its
README and docs say:

1. **What it is**: type and one line.
2. **How the loop runs**: what drives the repeat (shell loop, stop hook, harness, PR cycle).
3. **How it knows it is done**: the agent's own word, real checks, tests or CI.
4. **Where state lives**: files, git, a database, or the chat; does it survive `/clear`.
5. **Understanding first**: does it ask what you want and wait for a yes before building.
6. **Decisions and history**: are choices explained, and is there an audit trail.
7. **Stop limits**: budget, max rounds, or a finish condition.
8. **Agents, install, upkeep**: Claude Code, Codex or others; license; recent activity.

## Risks and limits

- **READMEs, not behavior.** We read what each project says about itself. We do not run the tools, so claims are unproven.
- **Our own project is in the table.** Goals is the author's project. It is scored on the same README-level evidence, and gaps are stated plainly.
- **Stars are a popularity signal only.** The 47,664 under `claude-plugins-official` is the whole plugin directory, not the Ralph plugin alone.
- **"Loop engineering" is a loose label.** Hits include tools, guides and a benchmark. The screen and the adjacent group exist for this reason.
- **A keyword screen is blunt.** It wrongly failed Loom once. Verdicts rest on reading, not on counts.
- **Search only finds what uses the phrase.** Agent frameworks that never say "loop engineering" or "Ralph" are out of scope.
- **Point in time.** Everything is a 2026-11-18 (UTC) snapshot. Stars and activity will drift.
