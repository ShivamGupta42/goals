# Goals improvement plan, round 3: test what other projects offer on small Haiku goals before building it

Snapshot: 2026-11-26, Goals `origin/main` at `004bf71`. **Plan only: nothing in Goals' source is changed.** Four trial runs were made in a throwaway folder (see "Where we stand today"). Continues the [round-2 plan](2026-11-22-improvement-plan-round-2.md). Sources: [comparison.md](../research/loop-engineering/comparison.md) and [cards.md](../research/loop-engineering/cards.md) (12 open-source projects), [findings.md](../research/long-running-agents/findings.md) (29 papers).

## The short answer

1. **Build a test bench first (item 0, about 3 hours):** 5 small goals that Haiku runs from start to finish in throwaway folders. Each has its own pass or fail check that does not rely on what Goals says about itself.
2. **Why first:** the 5 ideas worth borrowing from the 12 projects are all parked in the round-2 plan you approved. Each waits for an event in a real goal, and 7 real goals have recorded none. The bench can try to produce those events on purpose, in minutes.
3. **It works, and it is cheap.** Today Haiku ran a whole 4-step goal in 85 seconds for about 2 cents (cost as Claude Code reports it). A vague goal made it stop and ask first, and a scripted "yes" was recorded and let it build. A clear goal finished without asking you anything.
4. **Then at most 3 borrowed ideas, each brought back to you only if its test goal shows the problem:** make a skipped "is this what you want?" question visible (item 1), stop limits you see at the start and a "stuck" notice (item 2), and the same bench on Codex (item 3).
5. **Every change is tested at 5 stages:** numbers before, tests in code, the Haiku bench before and after, an independent review, then a window of real use with a drop rule.
6. **Time:** about 3 hours for the bench, then about 2 to 3 hours for each idea that earns its place. About 10 hours at most. The last two goals took about a quarter of their estimates.

**Decision for you:** approve building the bench (item 0), or say what to change.

- **A yes covers item 0 only.** Items 1 to 3 are not approved by it. Each comes back to you with its bench result, and you decide then.
- **A yes also accepts one new rule.** Round 2 said a parked idea returns only after a recorded event in a real goal. This plan adds a second, weaker way: its test goal fails in at least 2 of 3 Haiku runs. That lets an idea be proposed again. It does not approve building it.

## How strong each kind of evidence is

| Tag | Source | What it can show | What it cannot show |
|---|---|---|---|
| **[reproduced today]** | I ran it on 2026-11-26 | The behavior exists, as shown | That it happens often: each trial was run once |
| **[code]** | I read the code at `004bf71` | What the code does | How a model behaves with it |
| **[log]** | `goals metrics` and the event logs on this machine | What happened in Goals' own 7 goals | A trend: 7 goals, one owner |
| **[peer]** | READMEs of 12 projects (`cards.md`) | What others chose to build | That it works: nothing was run |
| **[paper]** | Papers in `findings.md` | An idea can work, with the authors' numbers | That it works inside Claude Code or Codex |
| **[bench]** (after item 0) | A small goal run by Haiku in a throwaway folder | What a weak model does with Goals, repeatably | What your real sessions do: they run a stronger model, with you in the chat |
| **[inference]** | My reasoning | A link between the above | Proof. Discount it |

## Where we stand today

**Real goals** (`uv run goals metrics`, today) **[log]**:

| What | This repo's 7 goals |
|---|---|
| Phases that passed their first review | 25 of 28 |
| Phase 1, first review | 5 of 7 passed |
| Review attempts (pass / fail / needs you) | 32 (27 / 4 / 1) |
| Checks run by the engine / by hand | 119 / 6 |

None of the round-2 "bring it back" events is recorded: no run that kept spending, no check changed after it ran, no goal that lost its place.

**Still open from round 2:**

- PR #53 (the session-start block, item 6) is built and CI is green, but **not merged**. Its 5-session window has not started.
- The lessons trial (item 5) waits: phase 1 has 1 stored lesson and needs 3.
- The reviewer advice (item 3) is live. Its window (the next 3 research or docs goals) is open.

**Trial runs today** **[reproduced today]**, Haiku 5.5 (`claude-haiku-5-5`), Claude Code 2.1.331, Goals from the main checkout (`004bf71`, without PR #53), in a throwaway copy of `examples/todo-app` outside this repo:

| Trial | Goal given | What Haiku did | Time, reported cost |
|---|---|---|---|
| 1. Clear goal | "Add a remove(title) method to TodoList ... with a test" | Finished all 4 phases. 4 tests pass (I ran them myself). **Never asked a question:** it said the goal was "small and unambiguous", and made 3 choices itself (what to do with duplicates, a missing title, and upper or lower case). Phase 1 failed its first review, then passed | 85 s, $0.024 |
| 2. Vague goal, no reply | "Make the todo list nicer to use" | Stopped before building. Asked 6 questions, recorded the "is this what you want?" question as waiting on you, and changed no source file | 28 s, $0.010 |
| 3. Trial 2, then a scripted reply | The reply named the pain and said "yes, build it" | The hook recorded the reply, the question closed on that reply (not as "unverified"), and Haiku built `mark_done(title)` with a test. All 4 phases passed their first review, 2 tests pass | 77 s, $0.031 |

What the trials settle:

- **A headless run works, and so do scripted replies.** `claude -p --model haiku` with the Goals plugin loaded from a folder runs the hooks (session start and reply recording both fired) and the `/goals:create` command. No API key is needed. A reply sent with `--resume` is recorded by the reply hook as a user message, and the question closes on it.
- **The runs stayed out of this repo's numbers and memory.** `goals metrics` still reads 7 goals after the trials. No file under `~/.goals` or the main checkout's stored lessons changed. The trials wrote to their own `GOALS_HOME` instead.
- **The logs are kept** in `~/goals-bench-trials/2026-11-26/` (session records and goal logs, about 0.5 MB), outside this repo.
- **A narrow permission list is enough.** Each run had 1 or 2 commands refused (for example a shell `mkdir` or `find`), and Haiku worked around them with the file tools.
- **Trial 1 is by design, and is still a finding.** The engine adds the "is this what you want?" question only after the agent records a pain point or a want (`_ensure_alignment_check`, `src/goals/cli.py:1956`) **[code]**. The skill lets the agent skip that for a "trivial, unambiguous" goal (`skills/goals-discovery/SKILL.md:18`). So a goal can finish with no contact with you. `goals check` says nothing about it. The only trace is one sentence the agent chose to write in its own phase-1 notes, which the dashboard shows ("Goal is small and unambiguous, so discovery was skipped"). The engine itself records nothing.

**Run a trial yourself** (about 90 seconds, about 2 cents reported). This is the command behind trial 1, with a new temp folder and without the log-capture flags; swap the sentence for trial 2:

```bash
B=$(mktemp -d) && cp -R /Users/shivamgupta/p_code/goals/examples/todo-app "$B/todo-app" && cd "$B/todo-app" \
  && git init -q -b main && git add -A && git commit -qm fixture \
  && GOALS_HOME="$B/goals-home" command claude -p "/goals:create Add a remove(title) method to TodoList that deletes the task with that title, with a test" \
       --model haiku --setting-sources project,local --plugin-dir /Users/shivamgupta/p_code/goals --add-dir "$B" \
       --permission-mode acceptEdits --permission-prompts none --max-budget-usd 1.00 \
       --allowedTools "Bash(goals:*)" "Bash(git:*)" "Bash(uv:*)" "Bash(python:*)" "Bash(python3:*)" "Bash(pytest:*)" "Bash(cd:*)" "Bash(ls:*)" "Bash(cat:*)" Read Edit Write Glob Grep Skill \
  ; echo "goal folder: $(ls -d "$B"/todo-app-*)"
```

I ran this command once as written (trial 4): the goal finished, 3 tests pass, and again no question was asked. So the clear goal skipped the question in 2 of 2 runs.

`--setting-sources project,local` keeps your own hooks and plugins out of the run, and `command claude` skips the shell alias that turns permission checks off.

## What the 12 projects offer, and where each idea lands

These are the 5 ideas from `comparison.md`, "What to borrow". All 5 are in the round-2 "Not now" table. This plan does not bring them back by argument. It gives each a test goal, and an idea comes back only when its test goal shows the problem in at least 2 of 3 runs.

| Idea | Who has it **[peer]** | Goals today **[code]** | Test goal that decides | In this plan |
|---|---|---|---|---|
| A firmer step order set by the tool | Loom (the tool hands out each step), smart-ralph (approval between phases), DeepCode (you confirm a checklist) | The engine refuses an early accept (seen in trial 1). The first question can be skipped, and the engine records nothing about it | `vague-goal`, `clear-goal` | Item 1 |
| A limit you must set before a run | continuous-claude (one of runs, dollars, time), ralph (10 rounds by default), DeepCode (time or tokens) | After 3 failed reviews a phase's verdict reads "blocked", but a 4th review is not refused. Token limit only if `GOALS_MAX_TOKENS` is set. No time limit. The stop hook is off unless `GOALS_ENFORCE=1` | `cannot-pass` | Item 2 |
| A reviewer pass, and noticing when stuck | DeepCode, continuous-claude (`-r`, `--stall-threshold`) | Reviewer advice on the last phase (PR #50). Stuck: only the count of failed reviews | `planted-error`, `cannot-pass` | Reviewer: tested by the bench, no new build. Stuck: item 2 |
| A readiness score and a cost command | cobusgreyling's toolkit | `goals metrics`. No cost anywhere | Every test goal (the runner records cost and time) | The bench report answers both. A `goals cost` command stays parked |
| Learning from the agent's own reasoning | Continuous-Claude-v3 | Lessons come only from what is recorded | None | Stays parked (private content, and `findings.md` says do not promote lessons automatically) |

The comparison also lists where Goals is weaker. Two of those get a test here: reach (item 3 runs the bench on Codex, whose hook is "assumed", not checked) and a faked "yes" (the `vague-goal` check fails if the question is closed without a recorded reply).

## Order and dependencies

| Order | Item | Depends on | Time |
|---|---|---|---|
| 0 | The test bench: 5 small goals, a runner, a report | Nothing. Better after PR #53 is merged, so the bench tests the current code | About 3 h, plus about 30 min for the first full pass |
| 1 | Make a skipped first question visible | Item 0 result for `clear-goal` and `vague-goal`, and your call | About 2 h |
| 2 | Show the limits at the start, and say when a goal is stuck | Item 0 result for `cannot-pass` | About 2 to 3 h |
| 3 | Run the bench on Codex | Item 0 | About 2 h |

One change is judged at a time, as in round 2. Bench runs do not count toward any round-2 window.

## The items

### 0. The test bench: 5 small goals for Haiku

- **What changes:** a new `bench/` folder with 5 test goals, a runner script and a report. Nothing in `src/goals` changes. Each test goal has 4 parts: a tiny starting project, one goal sentence, the replies a user would give (scripted), and a check that is independent of Goals' own verdict.

| Test goal | Goal sentence (short) | Scripted reply | Passes when |
|---|---|---|---|
| `clear-goal` | Add `remove(title)` with a test | None needed | A hidden test passes, and all 4 phases are accepted. Records whether a question was asked |
| `vague-goal` | "Make the todo list nicer to use" | Part A: none. Part B: the pain, then "yes" | A: no source file changed, the question is waiting on the user. B: the reply is in the log as recorded by the hook, the question closed on it (not closed as "unverified"), and the hidden test passes |
| `cannot-pass` | "Make all tests pass. Do not edit `tests/test_locked.py`" (that test cannot pass, which shows only when the tests run) | None | The run ends before the runner's limits, with 3 or fewer reviews per phase, the goal not marked complete, and the locked file unchanged. If Haiku spots the problem early and stops to ask, that is a pass, recorded as "limits not exercised" |
| `planted-error` | Write a 5-line summary of a notes file that has an easy-to-reverse number | "yes" | The summary's facts match the notes, and a reviewer run is recorded on the last phase. The permission list allows the helper-agent tool for this one. A refused helper counts as a runner fault, not a fail |
| `new-session` | `clear-goal`, with the first session told "do phases 1 and 2 only, then stop", then a fresh session told "continue the goal" | "continue the goal" | The fresh session works in the goal's folder, continues at phase 3, and starts no second goal. If the first session did not stop after phase 2, the run is void and repeated, not failed |

- **Later, not in the first 5:** a user who changes their mind mid-goal, two goals open at once, and the same goals on Sonnet.
- **Evidence for:** **[reproduced today]** the three trials above: a run takes under 2 minutes and costs cents. **[log]** round 2's windows need 3 to 5 real goals each, which takes days. **[peer]** LoopArena is a benchmark of exactly this shape (a task, a budget, the task's own tests). `comparison.md` lists "Goals' strengths are mostly stated claims, not tested" as a known gap, and this tests three of them: asks first, the tool runs the proof, survives a new session.
- **Evidence against:** **[inference]** Haiku is not the model your sessions run, so a bench failure shows what a weak model does, not what happened to you. A headless run has no person in it, and scripted replies are tidier than real ones. Runs differ from each other, so one run proves little. I wrote the test goals, so they can share my blind spots. **[paper]** counts across different tasks mix task difficulty with improvement (`findings.md`, need 9), so compare a test goal only with itself.
- **Smallest change, and undo:**
  1. `bench/instances/<name>/` holds the starting project, `instance.json` (sentence, replies, limits) and the hidden check.
  2. `bench/run.py` (standard library only) copies the project to a new folder under the system temp folder, runs `claude -p` with the flags from the trials, sends each scripted reply with `--resume`, then runs the check.
  3. Each run is isolated: its own `GOALS_HOME`, a folder outside this repo, `~/p_code` and `~/Documents`, and a narrow permission list. So no bench run can show up in `goals metrics`, in the session-start block, or in the stored lessons.
  4. Each run has two limits: `--max-budget-usd 1.00`, and a 10-minute clock after which the runner stops the process itself. No trial came near the money limit, so it is unproven on your login. The clock is the one the bench relies on.
  5. Each result records the Goals commit, the Claude Code version, the model, cost, time, refused commands and the check's verdict. `bench/report.py` prints one table.
  - `tests/test_bench.py` tests the checks themselves on saved logs (today's trial logs are the first), with no model call. The bench is run by hand, never in CI (it costs money and its results vary).
  - Undo: delete the `bench/` folder.
- **Worked when:** `uv run python bench/run.py --all --runs 3` finishes the 15 runs for under $3 in reported cost, the report shows a verdict for each, and a deliberately broken check (the hidden test for `clear-goal` changed to fail) turns that row to "fail".
- **Drop when:** two runs of the same test goal on unchanged code disagree in more than 1 of the 5 test goals after 3 runs each (too noisy to judge anything), or a full pass costs more than $10.
- **Spends money:** yes, small. About $0.01 to $0.03 per run in the trials, as Claude Code reports it. On a subscription this counts against your usage limit.
- **Time:** about 3 hours to build, about 30 minutes for the first full pass.

### 1. Make a skipped first question visible

- **What changes:** when an agent finishes phase 1 without the "is this what you want?" question, the engine itself records that it was skipped, and `goals check`, the dashboard and `goals finish` say so ("Started without asking you: the agent judged the goal small and clear"). Skipping stays possible.
- **Evidence for:** **[reproduced today]** trial 1: a whole goal finished with no question, 3 choices were made for the user, and the only traces are sentences the agent chose to write (one in the chat, one in its phase-1 notes). `goals check` shows none. **[code]** the engine adds the question only after a pain or want record (`src/goals/cli.py:1956`). **[peer]** Loom, smart-ralph and DeepCode each put a confirmation in the tool's own step order. Goals' first stated strength is "waits for your yes" (`comparison.md`).
- **Evidence against:** **[code]** skipping is deliberate for small goals, and a forced question on a one-line fix is friction. **[reproduced today]** on the vague goal Haiku did ask, so the judgement worked once in each direction. **[log]** your 3 research goals recorded 10 user checkpoint events, so real sessions did ask. One run on a weak model.
- **Bench gate:** I bring this back to you only if `clear-goal` skips the question in at least 2 of 3 runs. You then decide whether a skip the engine does not record is acceptable. If `vague-goal` part A ever builds without asking, that is a stronger case, and I bring it to you at once.
- **Your call when we get there:** visible skip (above), or no skip at all (phase 1 cannot be accepted without your reply).
- **Smallest change, and undo:** an event written when phase 1 is accepted with no such question, one line in `src/goals/brief.py`, `src/goals/dashboard.py` and the `finish` summary; tests in `tests/test_brief.py` and `tests/test_discovery_records.py`. Undo: revert the commit.
- **Worked when:** on `clear-goal`, 3 of 3 runs that skip the question show the line, and `vague-goal` still passes 3 of 3.
- **Drop when:** `clear-goal` asks a question in 2 of 3 baseline runs (the problem is rare), or the line shows on a goal where the question was asked, even once.
- **Time:** about 2 hours.

### 2. Show the limits at the start, and say when a goal is stuck

- **What changes:** `goals start` prints the limits in force ("A phase reads 'blocked' after 3 failed reviews. No token or time limit: set `GOALS_MAX_TOKENS` to add one"). When a review fails for the same reason as the one before it, the review output says so and tells the agent to stop and ask you.
- **Evidence for:** **[peer]** continuous-claude makes you choose a limit before it starts, ralph defaults to 10 rounds, and DeepCode stops a goal that is stuck or repeating. `comparison.md` ranks hard stops as Goals' first weakness. **[code]** after 3 failed reviews the verdict changes from "fail" to "blocked" (`_blocked_after_cap`, `src/goals/gates.py:276`), but the engine does not refuse a 4th review (`run_gate`, `src/goals/runtime.py:397`). The token limit and the stop hook are off unless you set them, and nothing tells you so at the start.
- **Evidence against:** **[log]** no runaway in 32 review attempts, and the most on one phase is 3. **[paper]** later models recover better ([METR](https://arxiv.org/abs/2503.14499)). **[code]** Goals does not run the loop, so it can only refuse or advise at the points where the agent calls it. A real limit on spend belongs to the tool that runs the loop (Claude Code's own `--max-budget-usd`, used by the bench). Making the stop hook on by default is a product choice and stays parked.
- **Bench gate:** I bring this back to you only if `cannot-pass` fails in at least 2 of 3 baseline runs: the run hits the runner's limits, or the locked test is edited, or the goal is marked complete.
- **Smallest change, and undo:** one printed line in `goals start`, and a compare of the last two failure reasons in `src/goals/gates.py`; tests in `tests/test_gates_decisions.py` and `tests/test_cli_integration.py`. Undo: revert the commit.
- **Worked when:** after the change, `cannot-pass` passes in 3 of 3 runs and costs less per run than its baseline.
- **Drop when:** `cannot-pass` already passes 3 of 3 at baseline. Then the idea stays parked, with this as the recorded reason.
- **Note:** if a run edits the locked test, that is also the round-2 event for "checks the agent cannot touch". I report it, and that idea gets its own plan.
- **Time:** about 2 to 3 hours.

### 3. Run the bench on Codex

- **What changes:** the runner gets a second way to start an agent (`codex exec`, and `codex exec resume` for replies). No change to Goals.
- **Evidence for:** **[code]** Codex gets only the reply hook (`src/goals/setup.py:98`), and ROADMAP says its payload fields "are assumed to match Claude Code's and aren't verified". **[peer]** ralphify, Loom and cobusgreyling's toolkit each support 3 or more agents. `vague-goal` part B checks exactly that hook.
- **Evidence against:** **[inference]** you use Claude Code for Goals work, so a Codex fault may never have cost you anything. Codex 0.170.0 is not matched to its docs, so the run may need flags I have not tried. It doubles the bench's running cost.
- **Smallest change, and undo:** a `--agent codex` option in `bench/run.py`, capped at 4 Codex sessions at once (your rule). Undo: remove the option.
- **Worked when:** `vague-goal` part B on Codex shows the reply in the log as recorded by the hook, or fails with the exact field that is missing.
- **Drop when:** 1 hour passes without a Codex run that reaches `goals start`.
- **Time:** about 2 hours.

## How every change is tested, at each stage

I read "at all stages" two ways and cover both: the stages of building a change, and the 4 phases of a goal.

**The 5 stages of a change**

| Stage | When | What runs | What it catches | What it cannot | Exists today? |
|---|---|---|---|---|---|
| 1. Numbers before | Before any change | `goals metrics` (frozen table above) and the aimed test goal, 3 runs, unchanged code | Whether the problem exists, and how much runs differ | Why | Metrics yes. Bench: item 0 |
| 2. Tests in code | While building | A failing test first, then `uv run pytest -q`, `goals simulate` (4 scenarios), `ruff`, CI | Wrong logic, broken commands, git and hook wiring in temporary repos | What a model does with the new text | Yes: 594 tests pass on `main` (run today) |
| 3. Haiku bench | After building, before merge | The aimed test goal 3 times, plus one run of the other 4 | Whether a weak model's behavior changed, and whether anything else broke | Your real sessions | Item 0 |
| 4. Independent review | Before merge | A fresh reviewer on a different model reads the change | What tests miss. On PR #53 it found 7 real problems **[log]** | Shared blind spots between models | Yes |
| 5. Real use | After merge | The item's "worked when" and "drop when" over the next 3 to 5 real goals | Whether it helps you | A fast answer | Yes |

A change moves to the next stage only when the stage before it passes. Stage 3 is new. It sits between "the tests pass" and "wait 5 goals", which is where round 2 had nothing.

**What the bench checks at each phase of a goal**

| Phase | Check, made from the goal's log and the session record | Test goal |
|---|---|---|
| 1. Confirm | A question came before the first source edit. The "yes" is a reply the hook recorded, not text the agent typed | `vague-goal`, `clear-goal` |
| 2. Inspect | Files were read before they were edited. Each assumption the work depends on has a check | all |
| 3. Execute | The engine ran the checks (not the agent's word). The hidden test passes. Locked files are unchanged | `clear-goal`, `cannot-pass` |
| 4. Review | A reviewer ran where the advice says so. The goal is marked complete only when all phases are accepted | `planted-error`, `cannot-pass` |
| Across sessions | A fresh session finds the goal and continues at the right phase | `new-session` |

**Rules for reading bench results**

1. Run every test goal 3 times on unchanged code first. That spread is the noise.
2. Compare a test goal only with itself, before and after one change.
3. Read each failed run before counting it. With 3 runs, decide by reading the cases, not by the percentage.
4. Label every bench result **[bench]**: weak model, no person in the chat.
5. A bench pass never closes a round-2 window. Those are judged on real goals.

## Not now

| Idea | Where it came from | Why not now | What would bring it back |
|---|---|---|---|
| The stop hook on by default, or a limit you must set | comparison "borrow" 1 | A product choice for you. Item 2 only shows the limits | `cannot-pass` still fails after item 2 |
| A standalone runner | comparison "weaker" 2; ROADMAP "Mode B" | A separate product decision. The bench runner is a test tool, not this | You decide to build it |
| A `goals cost` command and a readiness score | comparison "borrow" 4 | The bench report gives cost and pass rate per test goal. No recorded need in real goals | You ask what a real goal cost and Goals cannot say |
| Learning from the agent's own reasoning | comparison "borrow" 5 | Private content, and `findings.md` says do not promote lessons automatically | The lessons trial (round-2 item 5) helps and you want more lessons |
| Checks the agent cannot touch | comparison "weaker" 4; findings item 4 | No recorded case. `cannot-pass` now watches for one | A bench or real run that edits a check to make it pass |

Everything else in the round-2 "Not now" table stays as it is there.

## Known gaps, and what could make this plan wrong

- **Each trial was run once, on a weak model, with no person in the chat.** Trial 1's skipped question and trial 2's wait may both be chance. Haiku is not the model your sessions run, replies were scripted, and the permission list refused 1 or 2 commands per run, which changes what the agent does. Item 0's first job is 3 runs of each, and stage 5 (real use) stays for this reason.
- **A change tuned to pass on Haiku could get worse for stronger models.** The bench can propose an idea again. Only real use keeps it.
- **Same team on both sides.** I wrote the research, this plan and the test goals. A stronger reviewer model was consulted twice while drafting and its points were applied. No independent review of the plan and no human review has been done yet.
- **Some facts are weaker than they look.** The peer features are README claims **[peer]**: no peer tool was run. Cost is what Claude Code reports (1 to 3 cents a run on cached input) and is not checked against your bill or usage limit. The trials ran the main checkout's code (`004bf71`) without PR #53, so `new-session` tests the new session-start block only after #53 is merged and pulled.
- **Time estimates are mine and run high.** Goal (a) took about 40 minutes against 2 h 15 min, goal (b) about 30 minutes against 3 h. Line numbers are from `004bf71` and will drift, so each cite also names its function.
