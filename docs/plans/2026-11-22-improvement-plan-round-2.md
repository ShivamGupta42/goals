# Goals improvement plan, round 2: what is still open, in order

Snapshot: 2026-11-22, Goals `origin/main` at `96dc7ea`. **Plan only: nothing is changed yet.** Continues [improvement-plan.md](../research/long-running-agents/improvement-plan.md); also covers [comparison.md](../research/loop-engineering/comparison.md) and [findings.md](../research/long-running-agents/findings.md).

**Progress, as of 2026-11-23 (local time; log times below are UTC):** the plan was approved. Goal (a), fixes A, C and B, is merged (PR #51, `8882ff8`, CI green) and the installed `goals` has them. It took about 40 minutes of working time against the 2 h 15 min estimate (the goal log stamps the start at 19:05 UTC and the build verified at 19:28 UTC; the rest was waiting for replies and a review). The rest of this file is the plan as approved. Next: item 6.

## The short answer

1. **Four of the six earlier improvements are built** (items 1 to 4: PRs #47 and #50), but **not live on this machine**: the installed `goals` still runs `479e5da` until the main checkout is pulled. Open: items 5 and 6, quick fixes A and B, and one new find, C.
2. **Build it as three goals, in this order:** (a) the small fixes A, C and B, about 2 h 15 min; (b) item 6, the session-start block, about 3 h; (c) item 5, a lessons trial, about 4 h, started only when it has lessons to show. About 9 h in total.
3. **Fixes first:** A and C were reproduced today, and so was the mechanism behind B. All are cheap.
4. **Item 6 second:** reproduced today, and this session's own context block names a finished June goal.
5. **Item 5 last, off by default:** it can pass with no effect today (the last 3 goals passed phase 1 without it, and phase 1 has one stored lesson).
6. **Twelve other ideas are parked,** each with the event that would bring it back. The known gaps you listed are answered in the last section.

**Decision for you:** approve this order, or say what to move or drop.

## How strong each kind of evidence is

| Tag | Source | What it can show | What it cannot show |
|---|---|---|---|
| **[reproduced today]** | I ran the command on 2026-11-22 | The behavior exists, as shown | That it happens often |
| **[code]** | I read the code or ran a search on it | What the code does at `96dc7ea` | How it behaves in a real session |
| **[log]** | `goals metrics`, the event logs and Goals' memory entries on this machine | What happened in Goals' own goals | A trend: 12 logs, one owner |
| **[docs]** | The official hook pages, read by a helper model | What the tool documents | That the installed version behaves that way |
| **[paper]** | Papers in [findings.md](../research/long-running-agents/findings.md) | An idea can work, with the authors' numbers | That it works inside Claude Code or Codex |
| **[inference]** | My reasoning | A link between the above | Proof. Discount it |

Time estimates are mine and untested (see the last section).

## Where we stand today

| What | This repo's 5 goals (`uv run goals metrics`) | All 12 logs on this machine (the older script) | Earlier snapshot, 10 logs (2026-11-20) |
|---|---|---|---|
| Phases that passed their first review | 17 of 20 | 41 of 48 | 33 of 40 |
| Phase 1, first review | 3 of 5 passed | 8 passed, 4 failed | 6 passed, 4 failed |
| Review attempts (pass / fail / needs you) | 24 (19 / 4 / 1) | 56 (47 / 8 / 1) | 48 (39 / 8 / 1) |
| Checks run by the engine / by hand | 90 / 4 | 140 / 7 | 105 / 6 |

- The columns count different sets of goals, so they are **not comparable**. This table is the frozen baseline as of 2026-11-22. `goals metrics` reads only goals whose working folder still exists (`find_goal_logs`, `src/goals/metrics.py:85`) **[code]**, so a later run changes when a folder is removed. Judge against this table, not against a later run.
- The two goals built from items 1 to 4 passed all 8 of their phases first time. Two goals is not a trend.
- Reviews that did not pass in this repo (5): three were phase-1 failures in 2 goals (two were an assumption with no passing check; one was a check that ran and failed, the gate doing its job). Two were a checkpoint waiting for you, by design.

## What is done

| Item | What was built | Where | Still to judge |
|---|---|---|---|
| 1 | `goals metrics`, a read-only report | PR #47 | Done |
| 2 | Evidence lines in `goals loop improve` | PR #47 | Done |
| 3 | Reviewer advice on the last phase | PR #50 | Worked when: the next 3 research or docs goals record a reviewer run and at least one finds an issue. Drop when: 3 in a row find nothing |
| 4 | The `Checks:` line in `goals check`, `goals brief`, the dashboard and `goals finish` | PR #50 | Drop further hardening when: after 10 goals manual proof is still under 10% and no reviewer found a weak check |
| Skills | `present-plan`, and `explain-work` rewritten as a newest-first catch-up | personal dotfiles, `2ff87b6` (outside this repo) | First real use |

**Not live yet:** `goals` on your PATH is an editable install of the main checkout `/Users/shivamgupta/p_code/goals`, which is at `479e5da` and has no `src/goals/proof_summary.py` (checked today) **[reproduced today]**. Items 3 and 4 only reach real goals after a pull.

## Order and dependencies

| Order | Goal | Items | Depends on | Time |
|---|---|---|---|---|
| 0 | Make 3 and 4 live | `git -C /Users/shivamgupta/p_code/goals pull --ff-only`, then check that `goals check` prints a `Checks:` line | nothing | about 2 min |
| 1 | Small fixes | A, C, then B | nothing | about 45 min, 30 min, 1 h (stop at 30 min) |
| 2 | Session-start block | 6 | nothing | about 3 h, plus a 15-minute check |
| 3 | Lessons trial | 5 | item 6's window finished, and at least 3 lessons for the phase being tried | about 4 h, then 5 goals to judge |

**One change judged at a time.** Item 3's window (the next 3 research or docs goals) can run alongside anything, because it measures reviewer runs, not phase-1 passes. Item 6's window is 5 sessions after it is merged and pulled. Item 5's window starts only after item 6's window ends.

## The items

### A. `goals start` refuses a tree whose only change is an untracked file

- **What changes:** when `goals start` makes a new working folder, untracked files no longer block it, and the message names the ones that stay behind. Tracked changes still block.
- **Evidence for:** **[reproduced today]** in a throwaway repo with one untracked file, `goals start` printed "Refusing to create a goal from a dirty working tree. Commit or stash your changes first" and named nothing. **[log]** memory entry `M-f7e6501b` (medium, seen once) says it cost a turn. **[code]** `require_clean_repo` counts every `git status --porcelain` line (`src/goals/git_ops.py:129`), called at `src/goals/runtime.py:182`.
- **Evidence against:** an untracked file may be exactly the input the goal needs, and it will not exist in the new folder. That is why the message names it. Plain `--porcelain` shows a new folder as one line (this checkout shows `?? docs/plans/`), so the list must use `--untracked-files=all` to name the files inside it.
- **Smallest change, and undo:** ignore untracked entries for the new-folder case and print them with `--untracked-files=all`; a case in `tests/test_workspace.py`. Undo: revert the commit.
- **Worked when:** a goal starts with only an untracked file present (also one inside a new folder) and the message names that file, and a tracked change still refuses.
- **Drop when:** reverted if a goal ran without an input it needed, or if a new-folder start fails for any reason other than untracked files in the next 5 starts.
- **Time:** about 45 minutes.

### C. A raw U+2028 character in a recorded reply breaks that goal's event log (new)

- **What changes:** the loaders read each log line by splitting on the newline only, not with `str.splitlines()`, which also splits on U+2028, U+2029 and four other characters.
- **Evidence for:** **[reproduced today]** the writer (`event.model_dump_json()`, `src/goals/storage.py:232`) keeps a raw U+2028 (checked with pydantic: `'{"t":"a b"}'`). The loaders call `splitlines()` (`src/goals/storage.py:205`, `src/goals/audit.py:242`), which turns one such line into two, and both fail to parse as JSON (checked on a one-line file; I ran the writer and the split separately, not the whole `goals` command). The prompt hook stores the text of each reply of yours as an event, so one pasted character is enough. **[log]** memory entry `M-cc7c0d52` records the same defect (medium, seen once).
- **Evidence against:** **[log]** none of the 12 logs on this machine contains such a character, so it has not happened yet. **[inference]** such characters come from text copied off the web; how often you paste them is unknown.
- **Smallest change, and undo:** split on `"\n"` at both places (skip the empty last piece); a test with a reply that contains U+2028, for storage and for audit. Undo: revert the commit.
- **Worked when:** a goal whose log contains a raw U+2028 loads, and `goals check` runs on it (the test).
- **Drop when:** reverted if any of the 12 existing logs stops loading after the change.
- **Time:** about 30 minutes.

### B. A recorded judgement still produced a P0 "ask the user" finding

- **What changes:** first a test for the mechanism below; then a fix, or a clearer message if you decide that a judgement that is not linked to the finding should not count.
- **Evidence for:** **[log]** memory entry `M-aef30e06` (medium, seen once) says a recorded judgement (`JDG-7940dd17`) did not stop a P0 until the gap text was reworded. The June goal's log is lost, so its exact wording is unknown. **[reproduced today]** the reviewer's script (I re-ran it, it changes nothing on disk) shows the mechanism: the entry's own words give no finding; add the word "approval" with a recorded judgement that does not carry the source reference and you get a P0 ("Merge risk may need user approval"); add `phase:P1` to its refs and the P0 clears. **[code]** a finding is P0 only when it contains a user-decision word and no decision is matched, otherwise P1 (`src/goals/merge_readiness.py:359` and `:360`); matching is in `_covering_judgement_refs` (`:465`).
- **Evidence against:** "approval" was the reviewer's word, so this shows how a P0 can appear, not what happened in June.
- **Smallest change, and undo:** a test of the mechanism in `tests/test_merge_readiness.py`, then the fix. **Your decision when we get there:** should a judgement in the same phase that is not linked to the finding count? Undo: revert the commit.
- **Worked when:** the test fails before the fix and passes after, and `goals issues` on a goal with an unlinked recorded judgement either clears the P0 or tells you how to link it.
- **Drop when:** 30 minutes pass without a failing test.
- **Time:** about 1 hour at most.

### 6. Make the session-start block name the goal that is really in progress

- **What changes:** when the folder's own goal is finished or missing, the session-start hook also looks at the repo's other working folders. One active goal: name it. Several: list one line each and ask which. Add "Waiting on" and "Next" lines, goal first and next action last.
- **Where the lines go:** the session-start hook adds them after the context block (`src/goals/agent_hooks.py:82`). `render_context_block` and its other callers (`src/goals/portability.py:311`, `src/goals/cli.py:613`) stay unchanged. "Waiting on" comes from `GoalBrief.waiting_on` (`src/goals/models.py:483`). `GoalBrief` has no "next" field, so "Next" is the open checkpoint's title when the goal waits on you, and `goals next --agent <agent>` otherwise **[code]**.
- **Evidence for:** **[reproduced today]** `goals hooks session-start` run from the main checkout names the June marketing goal ("Current phase: none"); run from the long-running-agents folder it names that goal at phase 4. **[reproduced today]** this session's own context block is the June marketing goal. **[inference]** the cause is that the session started in the main checkout. **[reproduced today]** this session's transcript records SessionStart hook runs with source `compact` (16 lines, 8 compactions) under Claude Code 2.1.330, so the hook Goals already ships does re-run after a compaction and no new hook is needed. **[docs]** the hook may add context ([hooks reference](https://code.claude.com/docs/en/hooks)). **[paper]** goal first and next action last ([Lost in the Middle](https://arxiv.org/abs/2307.03172)). **[code]** the lookup already exists: `_candidate_goal_dirs` (`src/goals/agent_hooks.py:291`).
- **Evidence against:** **[paper]** compaction machinery has a mixed record (a plain summary prompt lost accuracy in [ACON](https://arxiv.org/abs/2510.00615): 43.5 vs 56.0 with no compression; [SWE-agent](https://arxiv.org/abs/2405.15793) keeps trimming off by default). This item adds no summarizer, only a correct pointer. **[inference]** with two active goals, picking one is a guess, so list them. **[reproduced today]** with goal 2 the only active goal, a session in any of the four finished checkouts would be pointed at it. That is the intent, but it can surprise. The hook fails open and only looks at goals of the same repo.
- **Smallest change, and undo:** change `session_start_payload` (`src/goals/agent_hooks.py:70`); tests with a temporary git repo that has a main checkout and one goal in a worktree. Undo: revert the commit, and the hook goes back to folder-only.
- **Worked when:** a session started in the main checkout with one goal active in a worktree gets that goal's name (the temporary-repo test), and after `/compact` in Claude Code the block is present again (a 15-minute manual check).
- **Drop when:** reverted to folder-only if the block names a goal other than the one you were working on, even once in the next 5 sessions (you tell me, and I record it with `goals memory record`).
- **Claude Code and Codex:** Claude Code yes. Codex gets no block from a hook today (only the prompt hook is installed, `_install_codex_user_prompt_hook` at `src/goals/setup.py:98`), so a Codex trial is parked (see "Not now").
- **Time:** about 3 hours, plus the 15-minute manual check.

### 5. Show past lessons at the phase they apply to (a flagged trial)

- **What changes:** `goals next` prints up to 3 stored lessons under "Lessons for this phase", each with its entry id. Only `learning` entries recorded at the current phase, newest first; friction and gap notes are left out because they describe Goals itself, not the work. It also writes an event listing the ids it showed, so the trial can be judged from the log. Behind `GOALS_PHASE_LESSONS=1`, off by default. `phase_lessons` does not exist yet **[code]**.
- **Start only when** the phase being tried has at least 3 `learning` entries. Phase 1 has 1 today (low severity) **[log]**.
- **Evidence for:** **[paper]** reusing lessons gains in the authors' own benchmarks: [ExpeL](https://arxiv.org/abs/2308.10144) 40% to 59% (ALFWorld), [ACE](https://arxiv.org/abs/2510.04618) 42.4 to 59.4 (AppWorld), [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952) 23.3% to 50.0% (AIME), [ReasoningBank](https://arxiv.org/abs/2509.25140) 40.5 to 48.8 (WebArena). **[log]** 3 of the 5 reviews that did not pass were phase-1 failures (in 2 goals), two of them an assumption with no passing check, which a lesson shown at that phase is aimed at. **[inference]** with a store this small, showing every match beats clever retrieval.
- **Evidence against:** **[paper]** [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952) says weak models amplify bad entries, and [ExpeL](https://arxiv.org/abs/2308.10144) found that feeding reflections into its rule extraction hurt (29% vs 39%); none of this was tested in a harness like Goals. **[log]** the two phase-1 misses are the two oldest goals; the 3 newest passed phase 1 first time without any flag, so "4 of 5" may already be the normal rate. **[log]** memory has 10 entries (counted today): 6 at phase 4, 2 at phase 2, one each at phases 1 and 3, and 6 of the 10 are `learning` entries. These failures are cheap (cleared within 3 attempts), so the possible gain is small. Entries are agent-written and unchecked, and memory is kept per machine, outside git. The rule that decides what counts as a lesson hides a single entry unless it is severity high or part of a cross-project pattern (`_is_actionable`, `src/goals/memory.py:344`) **[code]**.
- **Smallest change, and undo:** `phase_lessons(memory, phase_id, limit=3)` in `src/goals/memory.py`, printed by `goals next` (`src/goals/mode_a.py`); tests in `tests/test_memory.py` and `tests/test_mode_a.py`. Undo: leave the flag off, or revert.
- **Worked when:** over the next 5 goals with the flag on, the log shows lessons were shown at phase 1 in at least 3 of them, and none of the 5 phase-1 reviews fails for a reason a shown lesson names. The phase-1 first-pass count is recorded but is not the test, because the last 3 goals passed without the flag.
- **Drop when:** you judge a shown lesson wrong or misleading (I show you each case, you decide), a phase-1 review fails for a reason a shown lesson names, or fewer than 3 of the 5 goals had a lesson to show.
- **Time:** about 4 hours to build, then 5 goals to judge.

## Not now

| Idea | Where it came from | Why not now | What would bring it back |
|---|---|---|---|
| Per-goal `lessons.md` with counts and superseding (the write side) | findings item 1 | Read side first (item 5). Phase 1 is where failures cluster, and a per-goal file is empty there **[log]** | Item 5 helps over 5 goals |
| A `reflections.md` after a failed check | findings item 2 | Each failed review already prints its reasons, and each failed phase cleared within 3 attempts, except the one now waiting on you **[log]**. [Reflexion](https://arxiv.org/abs/2303.11366) showed no gain on WebShop or for weak models | A phase failing review 3 times for the same reason |
| A handoff file at context limits, a `PreCompact` hook that steers the summary, saving long tool output to files | findings item 3 | Summary prompts lost accuracy in [ACON](https://arxiv.org/abs/2510.00615). Goals records no compaction event that I found **[code]**, so whether a goal lost its place is unknown | A goal that visibly lost its place after a compaction, once item 6 is in |
| Checks the agent cannot touch: read-only check files, or checks run outside the agent | findings item 4 (second half); comparison "weaker" 4 | A Bash write gets around a blocked edit tool, and the paper case ([DGM](https://arxiv.org/abs/2505.22954)) is an agent rewriting its own checker. No recorded case of an agent changing a check after verify | A recorded case of that |
| A limit you must set before a run, and loop or stuck detection | comparison "borrow" 1 and 2; findings item 6 | No runaway in 56 review attempts (the cap is 3 per phase) **[log]**, a circuit breaker exists (`src/goals/agent_hooks.py:144`), and [METR](https://arxiv.org/abs/2503.14499) found later models recover better. The stop hook being opt-in is a product choice for you | A recorded run that kept spending without converging |
| A standalone runner, a "Loop Ready" score, a `cost` command | comparison "borrow" 4; ROADMAP "Mode B" | No evidence from the papers or the logs. The runner is a separate product decision | You decide to build the runner |
| A firmer tool-led step order (the engine asks for and checks each step) | comparison "borrow" 3 | Separate from the runner: the source says it still works through your agent, like Goals today. No evidence it would help | You want the engine, not the agent, to decide the next step |
| Learning from the agent's own reasoning, not only from your choices | comparison "borrow" 5 | **[inference]** it means reading the agent's reasoning, which can hold private content, and no log or paper here shows the need | Item 5 helps and you want more lessons |
| Tagging each run against failure modes and logging how often a lesson is used | findings item 5 (MAST) | Needs item 5's lessons to exist first, and counts across different tasks mix task difficulty with improvement | Item 5 helps |
| More agents than Claude Code and Codex | comparison "weaker" 3 | Even the Codex hook payload is "assumed", not verified; no recorded need | You start using a third agent |
| A session-start block for Codex | item 6 | Installed Codex 0.170.0 is not matched to its docs, so which events exist is unknown | A trial run shows SessionStart works in 0.170.0 |
| Decay and forgetting for observations | findings need 6 | `docs/GOAL_EXECUTION_MEMORY.md` says personalization reads only `preferences.md`, so a long observation log changes nothing today | Something starts reading observations |

## Known gaps, and what I did about each

These are the gaps you listed from the earlier plan, plus the ones this plan adds.

| Gap | What I did | Status |
|---|---|---|
| Same team on both sides (one agent wrote the research, the plan and most memory entries) | A fresh-context reviewer on a different model checked this plan against the code and the three source documents and raised 12 points. I re-ran or re-read the ones that changed the plan most (the installed version, fix B, the designs of items 5 and 6, the numbers) and they held; points 1, 7 and 8 I accepted from its reading. All are applied | Reduced, not removed: the reviewer is still an AI model |
| Baseline of 10 logs, one owner, only on this machine | Re-ran the baseline over every log found today: **12**, not 10. Added `goals metrics` numbers, which anyone can regenerate, and froze today's table. Three logs are still small demos and one older log has no check kinds | Reduced: still local, still not a trend |
| Paper gains are the authors' own, on their benchmarks | Cannot be fixed from here. Every item built on a paper is flagged, has a "drop when" rule, and item 5 is off by default | Unchanged, contained |
| Line numbers will drift | Re-checked every cited line at `96dc7ea` today. One had moved (the memory rule, now `memory.py:344` to `:350`) and is fixed; each cite also names its function | Closed for today |
| Hook facts came from a helper model and nothing was run | Ran what could be run: this session's transcript shows SessionStart runs with source `compact` under Claude Code 2.1.330 (the earlier plan said 2.1.329 was not matched). Codex 0.170.0 is still not matched to its docs | Claude Code: verified by a run. Codex: open |
| Effort estimates are mine and untested | Read the event logs of the two goals built from the earlier plan: 14.4 h and 8.9 h from first to last event, but that includes waiting for you, and the logs only stamp events, so active work cannot be recovered (the floor was about 1 h each). The estimates cannot be calibrated from the logs | Unchanged. From the next goal I write the start and finish times into its evidence, so the next plan can compare |
| No human has reviewed it | The review is open in Plannotator. Praise in chat is not approval; your Approve click or a typed yes is | Waits on you |

Gaps this plan adds:

- **Fix A was reproduced in a throwaway repo,** not in your real tree. **Fix B's mechanism was reproduced, but the June cause is lost.** **Fix C has never happened** in the 12 logs; it is a latent defect.
- **Item 5 can pass with no effect today** (3 of the last 3 goals passed phase 1 without it), which is why it has a precondition and a log event, and why phase-1 first-pass is not its test.
- **Two sources of numbers disagree in scope** (5 goals vs 12 logs), which is why the table keeps them in separate columns.
- **Line numbers** are from commit `96dc7ea` (2026-11-22) and will drift.
