# Goals improvement plan, driven by evidence

Snapshot: 2026-11-20. **Plan only: nothing in Goals' source was changed.** It builds on
[findings.md](findings.md) (29 papers and their code) and on the 12-project comparison from the
other goal (`docs/research/loop-engineering/comparison.md` on branch
`goal/research-about-other-github-open`), and adds a third stream: what Goals' own logs show.
Each item below is small enough to become one Goals goal (or one writing-plans implementation plan)
when you pick it.

## The short answer

1. **Measure before you build.** Item 1 reads the event logs Goals already writes. It costs about 2 hours and tells you whether any later item helped.
2. **Fix the improvement loop's own evidence first (item 2).** `goals loop improve` shows no evidence today, and every memory entry has an empty evidence field.
3. **The paper-driven "lessons file" changes shape.** In 10 goal logs, 5 of the 9 reviews that did not pass were at phase 1, where nothing has been written yet inside that goal. Most failures (6 of 8) were proof that was missing or unclear, and they repeat across projects. So the trial is a small read-side change (show past lessons at the phase they apply to), not a new per-goal file (item 5).
4. **Five of the six research recommendations are reshaped or postponed.** "Make improvement visible" starts as item 1 (existing events, no new prompt). "Protect the checks" becomes a visibility line (item 4). The context-limit handoff becomes a small fix to which goal the session-start block names (item 6). The reflections file and loop guards wait (see "Not now").
5. **Two items come from outside the papers:** an independent-review step (item 3, from two goals where a fresh reviewer found 15 issues each) and two cheap fixes for friction you hit.
6. **Every item has a stop rule.** The papers' gains are self-reported on benchmarks, and none was tested inside a harness like Goals.

## How strong each kind of evidence is

| Tag | Source | What it can show | What it cannot show |
|---|---|---|---|
| **[paper]** | 29 papers and the code of 25 ([findings.md](findings.md)) | An idea can work, with the authors' numbers | That it works inside Claude Code or Codex. Every number is the authors' own, on their benchmark |
| **[peer]** | READMEs of 12 projects (`comparison.md`) | What others chose to build | Behavior: nothing was run |
| **[log]** | Goals' own event logs (10 found) and `goals memory`, read today | What actually happened in Goals | Anything general: 10 goals, 40 phases, one owner. The logs do not record which agent or model ran them |
| **[inference]** | My reasoning | A link between the above | Proof. Marked so you can discount it |

## What Goals' own logs say today (the baseline)

Computed by [tools/baseline_events.py](tools/baseline_events.py) over each goal's `events.jsonl`
(read-only, stdlib only, lint clean). Proof counts use the latest evidence submitted for each phase.
A first count over folders named `goals*` found only 3 logs; a search for every
`.agent-workflow/goals/*/events.jsonl` under `~/p_code` and `~/Documents` found **10**. Logs on other
disks or deleted since are not counted. Other projects' goals are counted but not named.

| Goals counted | Phases that passed their first review | Review attempts (pass / fail / needs you) | Proof checks (auto / manual / waived) | User checkpoint events |
|---|---|---|---|---|
| The 3 goals in this repo (marketing analysis, loop-engineering research, long-running agents research) | 9 of 12 | 16 (11 / 4 / 1) | 55 / 3 / 0 | 10 |
| 7 goals in other projects (3 of them small demos, by their folder names) | 24 of 28 | 32 (28 / 4 / 0) | 50 / 3 / 0 | 0 |
| **Total, 10 goals** | **33 of 40** | **48 (39 / 8 / 1)** | **105 / 6 / 0** | **10** |

First review by phase, over all 10: phase 1 passed 6 and failed 4, phase 2 passed 9 and failed 1, phase 3 passed 10 of 10, phase 4 passed 8 and failed 2.

What this says, and how far to trust it:

- **Trouble clusters at phase 1, and it is about proof set-up.** Of the 9 reviews that did not pass, 5 were at phase 1. Of the 8 failures, 6 were proof that was missing or unclear (a criterion with no valid check, ambiguous criteria, or a load-bearing assumption with no passing falsifier), 1 was a check that ran and failed (the gate did its job), and 1 was a required checkpoint waiting for a reply, which is by design. Each phase that failed passed within 3 attempts, except the one still waiting on you.
- **These failures are cheap.** The gate names what is missing, and each was fixed on a later attempt. The gain from avoiding them is one review round in 4 of 10 goals at phase 1, not a failed goal.
- **Manual proof is rare: 6 of 111 checks (5%), and none waived.** One June log has no check kinds recorded (older format) and is left out of the proof counts. Whether the 105 auto checks are strong was not measured.
- **One clean phase 1 does not stand out.** The third goal in this repo passed phase 1 on its first review after the lesson was recorded (`M-6e92e4ed`, "a load-bearing assumption needs a runnable check"), but 6 of 10 goals did anyway, and it ran in the same session as the goal before it. Memory and plain conversation context cannot be told apart.
- **Memory has 9 entries from 3 goals** (two of them from this repo's research goals, one from a June goal whose log was not found), and all 9 have an empty `evidence_refs`. One suggestion comes out of them (see item 2).
- **Too small for a verdict.** 40 phases show where the failures cluster, not a trend. The baseline is there to catch harm and to give later changes something to be compared against.

## Order and dependencies

```
 1 baseline report ──────────────┐
 2 evidence in `loop improve` ───┼─► 5 past lessons at the right phase (trial)
                                 │      (judged against 1, shows ids from 2)
 3 independent review step       │   independent, text only
 4 proof-strength line           │   independent
 6 session-start block fix ──────┘   judged against 1; Claude Code only at first
 quick fixes A, B                    independent
```

## The items

Time estimates are for one engineer-agent session, including tests.

### 1. A baseline report: `goals metrics` (read-only)

- **Gap:** Goals has no measure across goals (findings, need 9: "lacks"). Only a count per friction note exists (`src/goals/memory.py:268`). The data is already there: every change is appended to `events.jsonl` (`src/goals/storage.py:226`).
- **Evidence for:** **[paper]** adaptation is measured as before/after on a stream of tasks ([AWM](https://arxiv.org/abs/2409.07429), [ReasoningBank](https://arxiv.org/abs/2509.25140)), repeated passes ([Memento](https://arxiv.org/abs/2508.16153)) or items over iterations ([Voyager](https://arxiv.org/abs/2305.16291)). All need a baseline first. **[log]** the prototype is about 70 lines and already produces the table above.
- **Evidence against:** **[paper]** curves across different tasks cannot be compared (findings, need 9), and these 10 goals differ a lot in size. **[inference]** a number the agent can see can become a target: it could avoid failed reviews by writing weaker checks. Keep it out of the agent's prompt.
- **Smallest change:** new `src/goals/metrics.py` (a pure function over each goal's events, the same logic as the prototype), a `goals metrics` command beside `brief` (`src/goals/cli.py:702`), and `tests/test_metrics.py`. Scan the goal worktrees with `goal_worktrees` (`src/goals/git_ops.py:93`), because goals live in separate working folders. No change to the event format.
- **Claude Code and Codex:** both. It is a command over files.
- **Worked when:** `goals metrics` on this machine prints the same totals as the table above. **Drop when:** nobody opens it after 10 goals.
- **Time:** about 2 hours.

### 2. Make `goals loop improve` show its evidence, and give memory entries real evidence

- **Gap:** I ran `goals loop improve` today. It printed one line, `[execution] Improve validation checks after learning: Add or improve validation coverage.`, and said 0 can be applied. Three causes:
  1. The printer never prints the evidence: `render_loop_improvement_plan` prints only the title and a fixed sentence (`src/goals/loop_improve.py:335`).
  2. The sentence comes from the entry's area, not its content: four learnings about research-checking practice became "add pytest coverage" plus `uv run pytest -q` (`src/goals/memory.py:382`, `:403`).
  3. There is nothing to print: all 9 entries have empty `evidence_refs` (`--evidence` is optional, `src/goals/cli.py:1100`).
- **Evidence for:** **[log]** the run above. **[paper]** the memory systems that work keep the source with each entry: [ExpeL](https://arxiv.org/abs/2308.10144) rules carry counts, [Zep](https://arxiv.org/abs/2501.13956) end-dates facts, and findings item 1 says a lesson is only as good as the check behind it. Trust V1 items I-16, I-42 and I-47 already plan to surface suggestions; this is the missing "with evidence" half.
- **Evidence against:** **[log]** hiding singletons is deliberate (`_is_actionable`, `src/goals/memory.py:328`: two or more entries, or one high). Printing note text makes the output longer (Trust V1 I-25 already worries about a wall of text). Check `goals memory absorb` first, because it may already attach references.
- **Smallest change:** (a) `goals memory record` attaches the id of the active goal's latest event for that phase to `evidence_refs` when `--evidence` is not given (events carry an `event_id`; entries already store the goal and phase ids, so copying those would add nothing), and leaves it empty when no goal is active; (b) the `loop improve` printer adds the first 120 characters of up to 3 entry notes and their ids under each line; (c) cases in `tests/test_loop_improve.py` and `tests/test_memory.py`.
- **Claude Code and Codex:** both. It is a command over files.
- **Worked when:** `goals loop improve` here prints the four notes and their ids. **Drop when:** it does not apply; this is a defect fix, so no stop rule beyond a complaint about output length.
- **Time:** about 1.5 hours.

### 3. Independent review as a named step before closing a research or docs goal

- **Gap:** the engine only insists that proof was executed (`src/goals/gates.py:137`: "the engine never decides *what* to test"), so it cannot check whether a claim means what its source says. Nothing in phase 4's default text (`src/goals/runtime.py:96`) or in the bundled skills and commands mentions an independent or fresh-context reviewer (I searched `skills/` and `commands/` for "independent", "fresh context" and "reviewer": no match).
- **Evidence for:** **[log]** in both research goals a fresh reviewer found 15 issues after a script had already confirmed every quote, including a reversed paper result (`M-b37df9be`, `M-cd5b977c`, both severity high). One high entry is enough to be actionable under Goals' own rule (`src/goals/memory.py:328`). **[peer]** DeepCode has an optional independent reviewer per requirement, and continuous-claude has `-r` reviewer passes, with a different model if you like (`comparison.md`, "What to borrow" 2).
- **Evidence against:** **[log]** both cases were research goals whose output is claims. For code goals the executed tests are the proof, and no log shows a reviewer on code. The reviewer was another Claude model (Opus), so it can share blind spots. **[paper]** a model judge is imperfect: [ReasoningBank](https://arxiv.org/abs/2509.25140) held up with a judge at 72.7% accuracy, so treat a reviewer as extra eyes, not as a gate (findings "Do not copy": a single LLM judge as the only gate). The same agent wrote both goals and the memory, so the lesson is the agent's own.
- **Smallest change:** text only. Add a sentence to the phase 4 prompt that `goals next` prints and a short paragraph to `commands/create.md`: for goals whose result is claims, run a fresh-context reviewer on the deliverable, check each of its findings against the source before applying it, and record the count as a manual verification with its rationale. Not a gate. A case in `tests/test_mode_a.py` asserts the text appears.
- **Claude Code and Codex:** both. It is wording in the `next` output.
- **Worked when:** in the next 3 research or docs goals, a reviewer run is recorded and at least one issue is found. **Drop when:** 3 in a row find nothing material; then make it optional.
- **Time:** about 1 hour.

### 4. Show how strong the proof is (the visibility half of "protect the checks")

- **Gap:** a manual or waived check counts for an acceptance criterion with any non-empty rationale (`src/goals/gates.py:270`), and the agent picks what to check. `goals check`, the dashboard and `goals finish` do not say how much of the proof is machine-run.
- **Evidence for:** **[paper]** agent-written tests let through false passes in [Reflexion](https://arxiv.org/abs/2303.11366) (16.3% on MBPP Python), and one [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) variant deleted the markers its checker used. **[log]** memory entry `M-2347c1ec` (gap, medium) flagged the same.
- **Evidence against:** **[log]** manual proof is rare here (3 of 58, none waived). It is also deliberate: `docs/WORKFLOW_IMPROVEMENTS.md:56` says "Treat manual UX review as first-class evidence". **[inference]** the paper cases were agent-written benchmark tests and a self-modifying agent, which is further from Goals' evidence file. A hook that blocks edits to check files would not stop a Bash write, so the read-only half of the research recommendation is not worth building now (see "Not now").
- **Smallest change:** one line in `goals check`/`brief`, the dashboard and the `goals finish` summary: `Proof: 18 auto checks passed, 1 manual (P4.C3), 0 waived`. Files: `src/goals/brief.py`, `src/goals/dashboard.py`, `src/goals/cli.py:441` (`finish`); cases in `tests/test_brief.py`.
- **Claude Code and Codex:** both.
- **Worked when:** the line shows in all three places. **Drop further hardening when:** after 10 goals the manual share is still under 10% and no reviewer found a weak check.
- **Time:** about 2 hours.

### 5. Show past lessons at the phase they apply to (a flagged trial)

- **Gap:** the research's largest cluster gains by reusing lessons from earlier runs ([ExpeL](https://arxiv.org/abs/2308.10144) 40% to 59% on ALFWorld, [ACE](https://arxiv.org/abs/2510.04618) 42.4 to 59.4 on AppWorld, [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952) 23.3% to 50.0% on AIME, [ReasoningBank](https://arxiv.org/abs/2509.25140) 40.5 to 48.8 on WebArena). Goals records lessons (`goals memory record`) but `next --full` shows only the top 5 actionable suggestions, ranked by severity and count (`src/goals/mode_a.py:34`), not the entries that match the phase you are in.
- **How this differs from findings item 1 (a per-goal `lessons.md` written at phase end):** **[log]** 5 of the 9 non-pass reviews were at phase 1, where a per-goal file has nothing yet, and the same proof set-up failures repeat across goals (phase 1 failed first review in 4 of 10 goals). So lessons have to cross goals. All 9 existing entries already carry a phase id (1 at phase 1, 2 at phase 2, 1 at phase 3, 5 at phase 4), so matching by phase needs no new store. Phase 1 has only one lesson so far (low severity), so the trial would show very little there at first. **[inference]** read first, write later: a write side with counts and superseding is only worth building if showing existing lessons helps.
- **Evidence for:** **[paper]** as above, plus [Mem0](https://arxiv.org/abs/2504.19413) scoring below full context on LOCOMO (66.88 vs 72.90): when the store is small (9 entries), including all the matching ones beats clever retrieval. **[log]** 6 of the 8 failures were proof set-up that the gate already names, and a lesson shown at the start of that phase is aimed at exactly that. The one clean phase 1 after a recorded lesson does not stand out (baseline above).
- **Evidence against:** **[paper]** [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952) says weak models amplify bad entries, and [ACE](https://arxiv.org/abs/2510.04618) says feedback quality decides. Entries here are agent-written and unchecked. [ExpeL](https://arxiv.org/abs/2308.10144) found some added text hurts (29% vs 39%). None of this was tested in a harness like Goals. **[log]** these failures are cheap (one extra review round, then a pass), so the possible gain is small. The current rule hides singletons on purpose (`src/goals/memory.py:328`), and memory is stored per machine, outside git (`.git/info/exclude` lists `.agent-workflow/self-evolution/`).
- **Smallest change:** a function `phase_lessons(memory, phase_id, limit=3)` in `src/goals/memory.py` that returns the learning and friction entries recorded against that phase id, newest first; `goals next` prints each one's note and entry id under "Lessons for this phase" (the id lets you trace it, which builds on item 2); behind an environment flag `GOALS_PHASE_LESSONS=1`. Tests in `tests/test_memory.py` and `tests/test_mode_a.py`.
- **Claude Code and Codex:** both. It is wording in the `next` output.
- **Worked when:** over the next 5 goals with the flag on, phase 1 passes its first review in at least 4 of the 5, compared with 6 of 10 in the baseline. With such small numbers, decide by reading each case, not by the percentage. **Drop when:** one shown lesson is wrong or misleading, or phase 1 first-pass does not improve after 5 goals.
- **Time:** about 4 hours to build, then 5 goals to judge.

### 6. Make the session-start block name the goal that is really in progress, and what it is waiting on

- **Gap:** this is the smaller, evidence-backed form of findings item 3 (a handoff step at context limits). The session-start hook picks the goal from the folder you started in (`active_goal_dir`, `src/goals/runtime.py:233`, used by `session_start_payload`, `src/goals/agent_hooks.py:70`). Goals live in separate working folders, so a session started in the main checkout never sees them. The block also has no "waiting on" or "next action" line (`render_context_block`, `src/goals/portability.py:268`).
- **Evidence for:** **[reproduced today]** `goals hooks session-start` run from the main checkout prints the June marketing goal (status `complete`, "Current phase: none"); run from the long-running-agents worktree it prints that goal at phase 4. So a session started in the main checkout never sees a goal that lives in a worktree, and the block in this session's own context is the stale one (whether it came from the session start or the re-run after compaction is unknown). **[docs]** Claude Code runs SessionStart again after compaction (`source` = `compact`) and lets it add context, so the hook Goals already has covers re-injection after a compaction; no new hook is needed ([hooks reference](https://code.claude.com/docs/en/hooks)). **[paper]** put the goal first and the next action last ([Lost in the Middle](https://arxiv.org/abs/2307.03172)). The prompt hook already finds goals in sibling folders (`_candidate_goal_dirs`, `src/goals/agent_hooks.py:291`), so the lookup exists.
- **Evidence against:** **[paper]** compaction machinery has a mixed record: a plain summary prompt lost accuracy in [ACON](https://arxiv.org/abs/2510.00615) (43.5 vs 56.0 with no compression), and [SWE-agent](https://arxiv.org/abs/2405.15793) keeps trimming off by default. This item avoids that: it adds no summarizer, only a correct pointer. **[inference]** with two active goals, picking one would be a guess; list them instead. Showing a sibling folder's goal in a session about something else could mislead; the hook fails open (`""`) and only looks at goals of the same repo.
- **Smallest change:** in `session_start_payload`, when the folder's own goal is finished or absent, also look at the repo's goal folders; if exactly one is active use it, if several print one line each and ask the user to say which. Add two lines from `build_goal_brief` ("Waiting on: ..." and "Next: ..."), goal first and next action last. Tests with a temporary git repo that has a main checkout and one worktree goal, in `tests/test_plugin.py` or a new `tests/test_session_start.py`.
- **Claude Code and Codex:** Claude Code yes, by the documented behavior above (not run here). Codex: Goals installs only the prompt hook there (`src/goals/setup.py:98`), so Codex gets no block from a hook today. Codex documents a SessionStart event and `hooks.json`, but the page does not say which events exist in 0.170.0 (the installed version), so adding it needs a trial run first.
- **Worked when:** a session started in the main checkout with one goal active in a worktree gets that goal's name (the temporary-repo test), and after `/compact` in Claude Code the block is present again (a 15-minute manual check). **Drop (revert to folder-only) when:** the block names the wrong goal even once in the next 5 sessions.
- **Time:** about 2 hours, plus the manual check.

## Hook check: what the plan relies on

A helper read the official hook pages and answered from them (nothing was run). Quotes were extracted by a fetch tool, not checked byte by byte, so spot-check before reusing one.

| Need | Claude Code ([docs](https://code.claude.com/docs/en/hooks)) | Codex ([docs](https://learn.chatgpt.com/docs/hooks)) |
|---|---|---|
| SessionStart runs again after compaction and can add context | Yes: source `compact`; `additionalContext` supported | SessionStart event listed; compaction source not documented |
| A hook before compaction | `PreCompact` (`trigger` manual or auto). Its output becomes instructions for the summary, and exit code 2 blocks compaction | `PreCompact` and `PostCompact` listed. Blocking is documented; steering the summary is not |
| Block an edit to a given file | `PreToolUse` deny by exit code 2 or `permissionDecision: "deny"`; the file is in `tool_input.file_path` | Deny is documented; filtering by path is not. Docs say: "Treat tool hooks as a useful guardrail, not a complete enforcement boundary." |
| Hook input | JSON on stdin with common fields including `transcript_path` | JSON on stdin with `session_id`, `cwd`, `transcript_path` |
| Available in the installed version | Claude Code 2.1.329 was not matched against the docs | Docs give no version, so whether all 14 listed events exist in 0.170.0 is not documented |

Only item 6 depends on hooks, and only on a hook Goals already ships for Claude Code.

## Two quick fixes from first-hand friction (one occurrence each)

Goals' own rule hides a single entry unless it is severity high (`src/goals/memory.py:328`), and
both of these are medium and seen once. They are listed because each is cheap and one cost you a
turn. Neither is paper-driven.

### A. `goals start` refuses a tree whose only change is an untracked file (`M-f7e6501b`)

- **Gap:** `require_clean_repo` counts every `git status --porcelain` line, untracked files included (`src/goals/git_ops.py:129`), and goal start calls it with only Goals' own folders ignored (`src/goals/runtime.py:182`). A new working folder is a fresh checkout, so an untracked file cannot be lost by it. You had to move your draft out of the repo before the goal could start.
- **Evidence for / against:** **[log]** one entry (medium) and one real turn lost. Against: an untracked file may be exactly the input the goal should work on, and it will not exist in the new folder.
- **Smallest change:** when creating a worktree, do not refuse for untracked files; print which ones will stay behind. Still refuse for tracked changes. Case in `tests/test_workspace.py`.
- **Both agents:** yes (CLI). **Worked when:** a goal starts with only an untracked file present and the message lists it. **Drop when:** not applicable (defect fix).
- **Time:** about 45 minutes.

### B. A recorded decision still produced a P0 "ask the user" finding (`M-aef30e06`)

- **Gap:** `_merge_risk_findings` makes a finding for any evidence text that matches the risk or user-decision word lists, and makes it P0 when no decision is matched to that text (`src/goals/merge_readiness.py:346`, word lists at `:45` and `:57`, decision matching in `_risk_status` at `:454`). The entry says the decision was already recorded and `merge-check` was clean, yet `goals issues` escalated until the gap text was reworded.
- **Evidence for / against:** **[log]** one entry (medium), from a June goal (`figure-out-how-do-people-market-and-get-distribu`) whose log was not found, so it cannot be re-read. **Not reproduced today**, so the cause (word match versus how a decision is matched to a text by `_risk_status`) is unconfirmed.
- **Smallest change:** write a failing test with the wording from the entry in `tests/test_merge_readiness.py`; fix the matching only if the test fails. Give up after 30 minutes if it cannot be reproduced.
- **Both agents:** yes (CLI). **Time:** about 1 hour.

## Not now

| Idea | Where it came from | Why not now | What would change it |
|---|---|---|---|
| Per-goal `lessons.md` with counts and superseding (write side) | findings item 1 | Read side first (item 5). 5 of the 9 non-pass reviews were at phase 1, where a per-goal file has nothing yet [log] | Item 5 helps over 5 goals |
| `reflections.md` after a failed check | findings item 2 | Each failed review already prints its reasons, and each failed phase cleared within 3 attempts [log]. Reflexion showed no gain on WebShop or for weak models ([Reflexion](https://arxiv.org/abs/2303.11366)) | A phase failing review 3 times for the same reason |
| Loop guards and a limit you must set before a run | findings item 6; `comparison.md` borrow 1 and 2 | No runaway in 48 reviews (most attempts on one phase: 3), a circuit breaker exists (`src/goals/agent_hooks.py:144`, cap from `src/goals/runtime.py:51`), and METR found later models recover better ([METR](https://arxiv.org/abs/2503.14499)). The stop hook being opt-in is a product choice for you | A recorded run that kept spending without converging |
| A compaction handoff file, a `PreCompact` hook that steers the summary, saving long tool output to files | findings item 3 | Both hooks exist (see "Hook check"), but a plain summary prompt lost accuracy in [ACON](https://arxiv.org/abs/2510.00615) (43.5 vs 56.0 with no compression), and [SWE-agent](https://arxiv.org/abs/2405.15793) trimming is off by default. No goal in the logs lost its place for this reason | A goal that visibly lost its place after a compaction, recorded in memory, once item 6 is in |
| Make check files read-only for the agent (by hook) | findings item 4, second half | A Bash write gets around a blocked edit tool, and the paper case ([DGM](https://arxiv.org/abs/2505.22954)) is an agent that rewrote its own checker | A recorded case of an agent changing a check after verify |
| A standalone loop runner, a "Loop Ready" score, a `cost` command | `comparison.md` borrow 3 and 4; ROADMAP "Mode B" | No evidence from the papers or the logs. The runner is a separate product decision | You decide to build the runner |
| Decay and forgetting for observations | findings need 6 | `docs/GOAL_EXECUTION_MEMORY.md` says personalization reads only `preferences.md`, so a long observation log changes nothing today | Something starts reading observations |

## Known gaps in this plan

- **Same team on both sides.** The research, this plan and 8 of the 9 memory entries it relies on were produced by one agent working in the Goals repo for its owner. The 15-issue reviews were done by other models, but the conclusions are not independent.
- **Baseline of 10 goal logs, one owner.** It shows where failures cluster, not a trend. Three of the logs are small demos, one older log has no check kinds, and logs outside `~/p_code` and `~/Documents` or deleted ones are missing. The `events.jsonl` files sit in `.agent-workflow/`, which is not committed, so the table can be reproduced only on this machine.
- **Paper gains are self-reported** on the authors' benchmarks and none was tested inside a harness like Goals. They support "worth a small trial", not "will work".
- **Line numbers** are from the Goals main checkout at commit `9a77d64` (2026-11-20) and will drift.
- **Hook facts** come from the official pages as read by a helper model, with fetch-tool quotes that were not checked byte by byte. Nothing was run in either agent, and the installed Codex (0.170.0) is not matched to the docs.
- **Effort estimates** are mine and were not tested.
- **A stronger reviewer model was consulted before and after drafting, and its points were applied; no human has reviewed this yet.**
