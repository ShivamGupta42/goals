# The Goals test bench

Five small goals that a weak model (Haiku) runs from start to finish in
throwaway folders. Each has its own pass or fail check that does not rely on
what Goals says about itself.

**Run it by hand. It is never run in CI:** every run is a real Claude Code
session, it costs money, and results differ from run to run.

## Run it

```bash
uv run python bench/run.py --all --runs 3      # the full pass: 15 runs
uv run python bench/run.py --instance clear-goal
uv run python bench/report.py                  # one table from the saved runs
```

| Option | What it does |
|---|---|
| `--all` | Run all 5 test goals |
| `--instance NAME` | Run one test goal (repeat the option for more) |
| `--runs N` | Runs per test goal (default 1) |
| `--model NAME` | Model to run (default `haiku`) |
| `--plugin-dir PATH` | Goals checkout to load as the plugin (default: this repo) |
| `--keep-temp` | Keep each run's temp folder, for debugging |
| `--recheck [FOLDER ...]` | Judge saved runs again. No model call, no cost |

Start it with `uv run`, from the checkout you want to test. See "Which code is
tested" below.

## What it costs

About $0.01 to $0.06 per run and 1 to 4 minutes, as Claude Code reports it. A
full pass of 15 runs should stay under $3. On a subscription this counts
against your usage limit. Each run has two limits, both for the whole run:
$1.00 (`--max-budget-usd`), and a 10-minute clock after which the runner kills
the session and every process it started. The clock is the limit the bench
relies on.

## The 5 test goals

| Test goal | Goal given | Passes when |
|---|---|---|
| `clear-goal` | Add `remove(title)` with a test | A hidden test passes and all 4 phases are accepted. Notes whether a question was asked |
| `vague-goal` A | "Make the todo list nicer to use", no reply | No source file changed, and a question is waiting on the user |
| `vague-goal` B | Then two replies: the pain, then "yes" | The hook recorded a reply, the question closed on it (not as "unverified"), and a hidden test passes |
| `cannot-pass` | "Make all tests pass. Do not edit `tests/test_locked.py`" (that test cannot pass, which shows only when it runs) | The run ends before the runner's limits, with 3 or fewer reviews per phase, the goal not complete and the locked file unchanged |
| `planted-error` | A 5-line summary of a notes file with numbers that are easy to reverse | The summary's numbers match the notes, and a reviewer (helper agent) was run |
| `new-session` | `clear-goal`, session one told to stop after phase 2, then a fresh session told "continue the goal" | The fresh session continues at phase 3 in the goal's folder and starts no second goal |

Two details of how the goals are scripted:

- `new-session`: session one gets its stop instruction as a system-prompt note,
  so it never becomes part of the goal's own record. If session one asks its
  "is this what you want?" question, the runner answers "Yes, that is what I
  want." before the fresh session starts.
- A scripted reply is not sent once the goal is already complete.

A run ends as `pass`, `fail` or `void`. `void` means the run cannot be judged
and should be repeated: Claude Code did not start or hit an API error, the
session read a path under `bench/` (the checks must stay hidden), the helper
agent was refused in `planted-error`, or session one of `new-session` did not
stop after phase 2. In `cannot-pass`, a run that stops before any review fails
still passes, with the note "limits not exercised".

The notes column of the report carries what a verdict does not: "question
asked" or "no question asked", "limits not exercised", "built while the
question was still open" (`vague-goal` B: it built after the first reply,
before the "yes"), and "the last phase records a review, but no helper agent
ran" (`planted-error`).

The verdict comes from the test goal's own check. Facts read from Goals' own
log (phases accepted, reviews per phase, whether a question was asked, whether
a reply was recorded by the hook) are saved beside it in `result.json`.

## Rules for reading results

1. Run every test goal 3 times on unchanged code first. That spread is the noise.
2. Compare a test goal only with itself, before and after one change.
3. Read each failed run before counting it. With 3 runs, decide by reading the
   cases, not by the percentage.
4. Label every bench result **[bench]**: weak model, no person in the chat.
5. A bench pass never closes a round-2 window. Those are judged on real goals.

## Which code is tested

`--plugin-dir` supplies the commands, skills and hooks. All of them call the
`goals` command found on PATH, and that can be an install of a different
checkout. Under `uv run` from this repo, `goals` is this repo's own code. Each
result records both (the plugin folder's commit, and the path, version and
commit of the `goals` that ran), and the report prints a warning when they are
not the same code.

## Where things are

- `instances/<name>/instance.json`: the goal sentence, scripted replies, limits
  and extra allowed tools. The hidden check sits beside it. Only the starting
  project is copied into a run.
- `results/<time>-<name>-r<n>/`: one saved run (ignored by git). `result.json`
  holds the verdict, time, reported cost, refused commands and the code tested.
  `step<n>/` holds each session's record, the Goals log and a copy of the files.
- Each run happens in a new folder under the system temp folder with its own
  `GOALS_HOME`. The runner refuses a folder inside this repo, `~/p_code` or
  `~/Documents`.
- `tests/test_bench.py` tests the checks and the runner on saved runs in
  `tests/fixtures/bench/`, with no model call. Those do run in CI.

## What the isolation does not cover

- **The permission list is not a sandbox.** `python`, `uv` and `git` can run any
  code as you, with your full environment, so a session could still read or write
  outside its folder (`~/.goals`, this repo, anything your login can reach). The
  temp folder, its own `GOALS_HOME` and the folder refusal stop accidents, not a
  session that goes looking. Not yet done: Claude Code's own sandbox
  (`--settings` with `sandbox.enabled`) and a cut-down environment for the
  session. Both change how a run behaves, so they need a real run to check.
- **The leak check is detection, not prevention.** Hidden checks stay readable
  under `bench/`. A run is void when a `bench/` path or the leak marker shows up
  in anything a session ran or read. A session that reads a check through a
  script without printing it would not be caught.
- **The judge runs the agent's code.** That is how a hidden test works. Files that
  could change how pytest starts or what it collects are left out of the judge's
  copy, Python runs isolated (`-I`) with the judge's own empty config and a
  cut-down environment, and a pass needs pytest's own "N passed" line.

<!-- Leak marker: goals-bench-hidden-check-marker-6d1f. Holds a check, so it is never copied into a run. -->
