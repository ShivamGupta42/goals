# What long-running agents need, how they keep adapting, and where Goals stands

Snapshot: 2026-11-19. Based on **29 research papers** and the open-source code of the 25 that
have it, plus Goals' own files described with the same rule. Papers were picked by a written
rubric ([README.md](README.md), [ranking.md](ranking.md)). Facts, quotes and code lines are in
[cards/](cards/): every paper quote and code snippet in them was looked up in its source and
found word for word. An independent review checked the claims below against the cards and sources.

## The short answer

1. **Memory has jobs, and the papers add rules for writing, updating and forgetting.** The big survey splits memory into factual, experiential and working ([survey](https://arxiv.org/abs/2512.13564)). This report splits experiential into episodic (what happened) and procedural (how to do things), because the systems differ. Most of the work is in the rules: what to write, when to update, what to forget.
2. **Agents keep adapting through text, not weights.** Reflections, rules, playbooks, skills and workflows that the model reads next time ([Reflexion](https://arxiv.org/abs/2303.11366), [ExpeL](https://arxiv.org/abs/2308.10144), [ACE](https://arxiv.org/abs/2510.04618), [Voyager](https://arxiv.org/abs/2305.16291), [AWM](https://arxiv.org/abs/2409.07429)).
3. **The best-supported writes follow a success check.** ReasoningBank's memory held up with a judge at 72.7% accuracy and improved when it also learned from failures. ACE and Dynamic Cheatsheet warn that weak feedback or weak models pollute the memory.
4. **The code usually does less than the paper.** ACE implements only ADD, Mem0's four-operation update is legacy, A-MEM never updates its counters, MemoryBank's forgetting formula differs. The simplest effective systems are plain files, a few prompts and a script; the bigger ones add vector stores, graph databases or trained retrievers.
5. **Goals is strong on its event log, decision-memory discipline and engine-run checks, and thin on task lessons, context help, retrieval and showing improvement.** The agent writes the checks, and manual and waived checks count with any non-empty rationale for acceptance criteria.

## What long-running agents need

Why it matters: the length of task an AI can finish half the time has doubled about every 207 days, and the length it finishes 80% of the time is 4 to 6 times shorter ([METR](https://arxiv.org/abs/2503.14499)). Beyond the window, recursive calls handled inputs of 6 to 11 million tokens ([Recursive Language Models](https://arxiv.org/abs/2512.24601)), and hard multi-tool tasks stay hard ([Memento](https://arxiv.org/abs/2508.16153)).

Nine needs came up again and again. Each one lists what the papers say, then what the code
actually does. Links go to the paper; the quotes and code lines are in the matching card in
[cards/](cards/).

### 1. Keep the window small and healthy (working memory)

- **Papers say:** position matters, with the best recall at the start or end of the context and the worst in the middle ([Lost in the Middle](https://arxiv.org/abs/2307.03172)). A plain think-act-observe loop only grows its prompt and has no overflow rule ([ReAct](https://arxiv.org/abs/2210.03629)). Fixes: collapse old observations to one line ([SWE-agent](https://arxiv.org/abs/2405.15793)); summarize near the limit and restart from the question plus the summary ([ReSum](https://arxiv.org/abs/2509.13313)); learn the compression prompt from failures, cutting peak tokens 26 to 54% ([ACON](https://arxiv.org/abs/2510.00615)); page memory in and out with a warning near the limit ([MemGPT](https://arxiv.org/abs/2310.08560)); keep the long input outside the prompt as a variable ([Recursive Language Models](https://arxiv.org/abs/2512.24601)).
- **Code shows:** SWE-agent's history trimming is off by default. RLM compacts at 85% of the window and cuts tool output at 20,000 characters. In Letta's archived MemGPT code the memory-pressure warning is off by default, and compaction starts at 0.9 of the window, not 100%.

### 2. Remember what happened (episodic memory)

- **Papers say:** keep a time-stamped stream and retrieve by recency, importance and relevance ([Generative Agents](https://arxiv.org/abs/2304.03442)); keep a bank of past cases with a verdict and learn which to retrieve ([Memento](https://arxiv.org/abs/2508.16153)); keep raw episodes as the base layer of a graph ([Zep](https://arxiv.org/abs/2501.13956)); cut dialogue into episodes at topic shifts ([EverMemOS](https://arxiv.org/abs/2601.02163)); write a reflection after each failed attempt ([Reflexion](https://arxiv.org/abs/2303.11366)).
- **Code shows:** Generative Agents' code uses retrieval weights of 0.5, 3 and 2 for recency, relevance and importance, not equal weights. Memento's retriever only changes when someone reruns the training script by hand.

### 3. Remember facts and who the user is (semantic memory)

- **Papers say:** extract facts and decide what to add, update or delete ([Mem0](https://arxiv.org/abs/2504.19413)); write linked notes that rewrite their neighbours ([A-MEM](https://arxiv.org/abs/2502.12110)); store facts with the dates they were true ([Zep](https://arxiv.org/abs/2501.13956)); build a graph over passages and walk it ([HippoRAG](https://arxiv.org/abs/2405.14831)); keep a user profile in a long-term tier ([Memory OS](https://arxiv.org/abs/2506.06326)).
- **Code shows:** Mem0's current add path is one ADD-only call; update and delete happen only through explicit calls. A-MEM stores read counts and last-used dates but never updates them. The open-source Zep code (Graphiti) lacks the commercial service's users, threads and memory API.

### 4. Remember how to do things (procedural memory)

- **Papers say:** save a skill only after a critic says it worked ([Voyager](https://arxiv.org/abs/2305.16291)); induce reusable workflows from judged successes ([Agent Workflow Memory](https://arxiv.org/abs/2409.07429)); keep an itemized playbook edited by small deltas ([ACE](https://arxiv.org/abs/2510.04618)); keep one rewritten cheat sheet ([Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952)); keep distilled strategies from successes and failures ([ReasoningBank](https://arxiv.org/abs/2509.25140)); keep numbered rules with counts ([ExpeL](https://arxiv.org/abs/2308.10144)).
- **Code shows:** ACE's code implements only ADD, not the in-place updates and pruning the paper describes. AWM regenerates the whole workflow file from all past successes each time and never reads the old file. Voyager never prunes its skill library.

### 5. Write only what is real (a write gate)

- **Papers say:** the better systems judge each finished attempt first, then write memory. Voyager uses a critic, AWM and ReasoningBank use an LLM judge, and ACE says it needs reliable feedback or the playbook gets polluted ([ACE](https://arxiv.org/abs/2510.04618)). A noisy judge was not fatal in ReasoningBank: its judge was 72.7% accurate, and results held across judge accuracies of 70 to 90%. Learning from failures as well as successes helped it (46.5 on success-only traces, 49.7 with failures) ([ReasoningBank](https://arxiv.org/abs/2509.25140)). A fixed check can still be gamed: one Darwin Gödel Machine variant deleted the markers its hallucination detector used ([Darwin Gödel Machine](https://arxiv.org/abs/2505.22954)), and Reflexion's agent-written unit tests let through false passes (16.3% on MBPP Python) ([Reflexion](https://arxiv.org/abs/2303.11366)).
- **Code shows:** ReasoningBank's parallel-scaling code labels a reward of 0 as success. Mem0 replaced its LLM "no-op" decision with an md5 duplicate check.

### 6. Update and forget without losing what matters

- **Papers say:** the field has no standard. Options seen: never forget ([ReasoningBank](https://arxiv.org/abs/2509.25140), [Voyager](https://arxiv.org/abs/2305.16291), [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954)); counts that delete at zero ([ExpeL](https://arxiv.org/abs/2308.10144)); mark old facts invalid with an end date instead of deleting ([Zep](https://arxiv.org/abs/2501.13956)); a forgetting curve that fades unused memories ([MemoryBank](https://arxiv.org/abs/2305.10250)); evict the coldest topic ([Memory OS](https://arxiv.org/abs/2506.06326)). The 107-page survey warns that over-aggressive pruning can erase rare but essential knowledge ([Memory in the Age of AI Agents](https://arxiv.org/abs/2512.13564)).
- **Code shows:** MemoryBank's code computes `(-t/5)*S` where the paper has `e^(-t/S)`, so higher strength forgets faster, and forgetting is off by default. Memory OS evicts by lowest access count, not lowest heat as in the paper. Generative Agents sets a 30-day expiry that nothing reads.

### 7. Find the right memory at the right time (retrieval)

- **Papers say:** embedding top-k is the common default; others add recency and importance ([Generative Agents](https://arxiv.org/abs/2304.03442)), graph walks ([HippoRAG](https://arxiv.org/abs/2405.14831)), or hybrid search with rerankers ([Zep](https://arxiv.org/abs/2501.13956)). Several systems skip retrieval and put the whole file in the prompt ([AWM](https://arxiv.org/abs/2409.07429), [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952)). How many to fetch matters: Memento found 4 cases best.
- **Code shows:** AWM ships FAISS retrieval that its own pipelines never call. ReasoningBank's default fetches only 1 past task.

### 8. Catch loops and early stops (failure control)

- **Papers say:** a study of 1,642 multi-agent traces found 14 failure modes in three groups: design problems 44.2%, misalignment 32.3%, weak verification 23.5% ([Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)). In METR's study, over a third of GPT-4's failures were repeated failed actions, against 2 of 32 for o1, and half of o1's failures were giving up too early; models since GPT-4o recover from mistakes better ([Measuring AI Ability to Complete Long Software Tasks](https://arxiv.org/abs/2503.14499)). ReAct can loop on its own earlier thoughts ([ReAct](https://arxiv.org/abs/2210.03629)).
- **Code shows:** SWE-agent caps re-queries at 3 and adds a guard that tells the model not to re-run a failed edit. METR is a measurement study and has no code.

### 9. Show that it is improving over time

- **Papers say:** adaptation is measured in different ways: items found over 160 iterations ([Voyager](https://arxiv.org/abs/2305.16291)), five repeated passes ([Memento](https://arxiv.org/abs/2508.16153)), a stream of tasks ([AWM](https://arxiv.org/abs/2409.07429), [ReasoningBank](https://arxiv.org/abs/2509.25140)), or before and after training ([ExpeL](https://arxiv.org/abs/2308.10144)). Benchmarks exist for recall (LoCoMo and LongMemEval, used by [Mem0](https://arxiv.org/abs/2504.19413), [Zep](https://arxiv.org/abs/2501.13956) and [EverMemOS](https://arxiv.org/abs/2601.02163)), and the 2025 survey has a section of benchmarks for memory, lifelong and self-evolving agents ([Memory in the Age of AI Agents](https://arxiv.org/abs/2512.13564)). But the tasks differ, so the improvement curves cannot be compared with each other.
- **Code shows:** the research code is a set of experiment runs, not a monitor. Memento's retriever changes only when someone reruns the training script by hand.

## How agents keep adapting (what changes between run 1 and run 100)

None of these change the model's weights. What changes is text the model reads next time, or the agent's own prompt or code.

| What changes | Papers | Gain the papers report | Weak point (the authors' or seen in the code) |
|---|---|---|---|
| Written reflections and rules | [Reflexion](https://arxiv.org/abs/2303.11366), [ExpeL](https://arxiv.org/abs/2308.10144) | ALFWorld 130 of 134 tasks (Reflexion); ExpeL ALFWorld 40% to 59% | Memory is a fixed window (Reflexion); text only and context grows (ExpeL) |
| A growing playbook or cheat sheet | [ACE](https://arxiv.org/abs/2510.04618), [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952), [ReasoningBank](https://arxiv.org/abs/2509.25140) | AppWorld 42.4 to 59.4 (ACE); AIME 23.3% to 50.0% (DC); WebArena 40.5 to 48.8 (ReasoningBank) | Needs a strong model and reliable feedback; weak models amplify mistakes |
| Skill and workflow libraries | [Voyager](https://arxiv.org/abs/2305.16291), [AWM](https://arxiv.org/abs/2409.07429) | 63 unique items, 3.3 times the baselines (Voyager); WebArena 35.5% vs 23.5% (AWM) | Wrong workflows from wrong trajectories (AWM); no pruning (Voyager) |
| A case bank with learned retrieval | [Memento](https://arxiv.org/abs/2508.16153) | GAIA 87.88% Pass@3 on validation; +4.7 to 9.6 points out of distribution | Bank saturates after about 3k tasks |
| Rewriting the prompt or the agent itself | [GEPA](https://arxiv.org/abs/2507.19457), [ACON](https://arxiv.org/abs/2510.00615), [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) | GEPA beats GRPO by 6% on average with up to 35 times fewer rollouts; DGM SWE-bench 20.0% to 50.0% | DGM cost about USD 22,000 per run and one variant gamed its checker |
| Memory stores that grow and link | [Mem0](https://arxiv.org/abs/2504.19413), [A-MEM](https://arxiv.org/abs/2502.12110), [Zep](https://arxiv.org/abs/2501.13956), [EverMemOS](https://arxiv.org/abs/2601.02163) | Mem0 91% lower p95 latency than full context; EverMemOS 93.05% on LoCoMo | Quality depends on the model that writes the notes |

**Where it did not help.** Mem0 scores below full context on LOCOMO (66.88 vs 72.90). Reflexion showed no gain on WebShop and none for weak models (StarChat 0.26 to 0.26). Memento's no-memory baseline also rose over its 5 iterations (78.65 to 84.47). ACE gains little on short-context tasks (HotPotQA, Game of 24). ExpeL found that feeding reflections into insight extraction hurt (29% vs 39%).

Four patterns repeat across these papers:

1. **The success signal matters, but a noisy one is survivable.** Gains come where there is a success check (tests, execution results, a judge). ReasoningBank's memory held up with a judge at 72.7% accuracy, while ACE says its playbook degrades without reliable feedback and Dynamic Cheatsheet says weak models amplify mistakes.
2. **Whole-file rewrites are risky, but not always fatal.** ACE names "context collapse" when a model rewrites the whole notes file and it shrinks, and uses small edits instead. Dynamic Cheatsheet rewrites its whole sheet each time and still gains a lot, but its code has no check against truncated rewrites.
3. **Growth is often unmanaged.** Many systems only add (ReasoningBank, Voyager, ACE's code, Mem0's current add path). The ones that prune each have a catch (see need 6).
4. **Adaptation is measured in different ways.** Voyager counts items over 160 iterations, Memento reports 5 iterations, AWM and ReasoningBank use a task stream, and ExpeL compares before and after training. The tasks differ, so these curves cannot be compared with each other. (The 2024 survey said no open benchmark existed for memory modules ([A Survey on the Memory Mechanism of LLM-based Agents](https://arxiv.org/abs/2404.13501)); the 2025 survey has a benchmark section.)

## What the code reveals

The papers describe more than the code does. Seven examples, each in its card:

- **ACE:** the paper has in-place updates and pruning; the code has only ADD, and the token budget appears only in a prompt.
- **Mem0:** the four-operation update prompt is legacy and never imported; the paper's numbers (LoCoMo 66.88) are not the README's newer score.
- **A-MEM:** `retrieval_count`, `last_accessed` and `evolution_history` are stored but never updated.
- **MemoryBank:** the forgetting formula in the code differs from the paper's.
- **Generative Agents:** recency is rank-based and, as the reader of the code saw it, looks inverted. The 30-day expiry it sets on thoughts is never read.
- **ReasoningBank:** the sequential-scaling prompts exist but nothing calls them.
- **MemGPT:** the original repo is now a landing page. The code lives on the `archive` branch of Letta, and the memory-pressure warning is off by default.

The practical lesson: the simplest effective systems (Reflexion, AWM, ACE, Dynamic Cheatsheet, ReasoningBank) are **plain files plus a few prompts plus a script that edits them**. The bigger ones add a vector store, a graph database or a trained retriever (Mem0, Zep, Letta, EverMemOS, A-MEM, Memento). A harness inside Claude Code or Codex can build the first kind directly.

## Where Goals stands against the nine needs

Goals is a small layer inside Claude Code and Codex that keeps plan, proof and decisions in plain
files and uses hooks. It was described with the same rule as every paper: only its own files, with
a quote or a file and line for each point ([cards/goals-self.md](cards/goals-self.md)). **has** =
covers the need as the research describes it. **partial** = covers part of it. **lacks** = nothing
found. Rows 4 and 7 also use file and line checks made after an independent review.

| Need | Goals today | Evidence in Goals' own files |
|---|---|---|
| 1. Window small and healthy | **partial.** The SessionStart hook injects a short goal block (objective, phase, acceptance). The prompt hook records your reply and injects nothing. No compaction, trimming or summary logic | `src/goals/agent_hooks.py:70` |
| 2. What happened (episodic) | **partial.** A solid log: every change is appended to a per-goal `events.jsonl`, and verified checks keep the exit code and an output hash. But it is only a log: nothing from it is pulled back into the agent's context automatically | `src/goals/storage.py:226` |
| 3. Facts and the user (semantic) | **partial.** `preferences.md` (yours) and `observations.md` (agent appends, one goal only). Discovery's pains and wants are recorded and can be superseded. User preferences and Discovery only; no project facts | `docs/GOAL_EXECUTION_MEMORY.md`, `src/goals/storage.py:559` |
| 4. How to do things (procedural) | **partial.** No automatic skill or task-lesson learning. But `goals memory record` stores friction, gap, learning and success notes about how Goals itself ran, and repeated friction becomes suggestions for improving its skills | `skills/README.md`, `src/goals/cli.py:1104`, `src/goals/memory.py:278` |
| 5. Write only what is real | **partial.** The engine runs auto checks and sets `ran` and `passed` from exit codes; the agent cannot set them. But the agent decides what to check ("the engine never decides *what* to test"), a manual or waived check counts for an acceptance criterion with any non-empty rationale, and memory writes have no origin check | `src/goals/runtime.py:459`, `src/goals/gates.py:137`, `src/goals/gates.py:273`, `src/goals/user_memory.py:112` |
| 6. Update and forget | **partial.** The event log is append-only; revising Discovery marks old pains and wants superseded; `goals user forget` removes preferences. Observations and friction notes only grow | `src/goals/user_memory.py:135`, `src/goals/storage.py:559` |
| 7. Find the right memory | **partial.** No search. Injection is fixed: the goal block, and with `next --full` the top 5 friction suggestions (ranked by severity, then count) and the first 5 preferences in file order | `src/goals/user_memory.py:337`, `src/goals/mode_a.py:34`, `src/goals/memory.py:278` |
| 8. Loops and early stops | **partial.** Opt-in stop hook that blocks stopping while the phase still has agent work; 3 failed reviews per phase or a token ceiling end the block; it fails open. No repeated-action detection | `src/goals/agent_hooks.py:122`, `src/goals/agent_hooks.py:188` |
| 9. Is it improving over time? | **lacks.** No metric or trend across goals or runs. Only a count per friction note | `src/goals/memory.py:268` |

### What Goals already does well

- **Checks the engine runs itself.** Acceptance on auto checks comes from exit codes, not from a model's say-so, which is a firmer base than the LLM judges most of these papers use. The catch is that the agent chooses what to check (see the gaps).
- **Careful decision memory, by design.** The docs say the agent only appends observations and never rewrites your preferences, and that a one-off choice becomes a standing preference only when you confirm it. That keeps a model from rewriting a whole notes file, the failure ACE calls context collapse ([ACE](https://arxiv.org/abs/2510.04618)). The code does not enforce it, though: nothing stops an agent from recording a preference itself.
- **A memory for how Goals ran.** Friction, gap, learning and success notes, with suggestions ranked by severity and count and shown in `next --full`. It is about improving Goals' own workflow, not lessons for your task, but it is the nearest thing to build on.
- **State on disk.** Plan, proof and decisions live in files, so they survive `/clear`. Only a short goal block is injected at session start, so nothing else comes back automatically.
- **Its own docs cite this literature.** `GOAL_EXECUTION_MEMORY.md` names Generative Agents, MemGPT, A-MEM and Mem0 as design sources.

### Where the research says Goals has gaps

- **No task-lessons memory.** The largest cluster of papers gains by writing lessons from past runs ([ExpeL](https://arxiv.org/abs/2308.10144), [ACE](https://arxiv.org/abs/2510.04618), [Dynamic Cheatsheet](https://arxiv.org/abs/2504.07952), [ReasoningBank](https://arxiv.org/abs/2509.25140), [AWM](https://arxiv.org/abs/2409.07429), [Voyager](https://arxiv.org/abs/2305.16291)). Goals has an engine-run gate that could decide what is worth writing, but nothing that turns finished phases into lessons for the next ones.
- **Gaps in its own gate.** The agent writes the checks, and manual or waived checks count for acceptance criteria with any non-empty rationale. Agent-written tests let through false passes in Reflexion (16.3% on MBPP Python, [Reflexion](https://arxiv.org/abs/2303.11366)), and one Darwin Gödel Machine variant deleted the markers its checker used ([DGM](https://arxiv.org/abs/2505.22954)). (Manual and waived checks do not count for load-bearing assumptions or auto-proof wants.)
- **No help at context limits.** No handoff or compaction step, while ReSum, ACON, MemGPT and SWE-agent all manage what stays in the window. State already on disk would make one easy to build.
- **Loop control is narrow.** METR found that early models often repeated failed actions (over a third of GPT-4's failures, against 2 of 32 for o1), that half of o1's failures were giving up early, and that models since GPT-4o recover better ([METR](https://arxiv.org/abs/2503.14499)). Goals' stop hook already blocks early stops. It does not notice a repeated action, which looks like a smaller risk with current models.
- **No way to show improvement.** This is the third thing you asked for: what changes between run 1 and run 100. Goals cannot show it today.
- **Growth without decay.** Its own docs say the observation log only grows.

## What to build next (ranked)

Each item uses only plain files, prompts and hooks, so it fits inside Claude Code and Codex.

1. **A per-goal `lessons.md`, written when a phase ends, from passes and from failures.** The verdict of the phase's auto check decides what a prompt may write: up to 3 short entries, each with the proof path, a use count and a last-used date. A script applies adds and count changes; the model never rewrites the file. Old entries are marked superseded, not deleted, and the file has a size cap. Build it on `goals memory`. Evidence: ExpeL (rules with counts), ACE (itemized playbook), ReasoningBank (it did better with failures included, 46.5 on success-only traces and 49.7 with failures), Zep (end-dated facts). *Watch for:* keep Reflexion-style reflections (item 2) out of lesson extraction, because ExpeL found they hurt (29% vs 39%); ACE's code only implements ADD; Dynamic Cheatsheet says weak models amplify bad entries; and a lesson is only as good as the check behind it (see item 4).
2. **A reflection note after a failed check.** A 2 to 5 sentence "tried, why it failed, new plan" appended to `reflections.md`, with the last 3 shown at the next attempt ([Reflexion](https://arxiv.org/abs/2303.11366)). *Watch for:* Reflexion showed no gain on WebShop and none for weak models.
3. **A handoff step at context limits.** A PreCompact or Stop hook writes a handoff file with fixed headings (ACON's: reasoning, variables, to-do, completed, guardrails) and only certain, sourced facts ([ACON](https://arxiv.org/abs/2510.00615), [ReSum](https://arxiv.org/abs/2509.13313)). A hook could also save long tool output to a file and keep a one-line stub (SWE-agent collapses old output to a one-line note; saving the full text is an addition, [SWE-agent](https://arxiv.org/abs/2405.15793), [RLM](https://arxiv.org/abs/2512.24601)). Put the goal first and the next action last in what is injected ([Lost in the Middle](https://arxiv.org/abs/2307.03172)). *Watch for:* a plain summary prompt lost accuracy in ACON (43.5 vs 56.0 with no compression), ReSum says generic summarizers struggle, and SWE-agent's trimming is off by default (its docstring says current models often do not need it). Test the handoff against no compaction before trusting it.
4. **Protect the checks.** In the dashboard and final report, show manual and waived checks as not machine-proven, and make check files read-only for the agent once set. Evidence: Reflexion's false passes from agent-written tests, and the Darwin Gödel Machine variant that deleted its checker's markers.
5. **Make improvement visible.** At each phase end a fresh-context prompt tags the run against a short list of failure modes (from MAST) and appends to a log; lesson use counts are logged too. Compare the same kind of task across runs, because counts across different tasks mix task difficulty with improvement. The papers measure adaptation in different ways (see need 9), so this would be Goals' own measure.
6. **Loop guards.** A hook counts identical failing commands and asks for a new approach or a written blocker. Lower priority than it looks: METR found later models recover from mistakes better, and Goals' stop hook already blocks early stops. Evidence: [MAST](https://arxiv.org/abs/2503.13657)'s failure modes (step repetition is one), SWE-agent's "do not re-run the same failed edit" guard.

**Do not copy:** a model rewriting a whole memory file (ACE's context collapse), a single LLM judge as the only gate, automatic promotion of lessons into global preferences (Goals' own rule), or memory that only grows with no cap.

## Known gaps in this research

- **Reading depth.** Each paper was read once by one agent, targeted at the memory, context and adaptation parts. All 115 paper quotes and 167 code snippets are word for word in their sources. One independent review (on Opus, because Fable was rate-limited) found 15 issues, which were checked against the sources and applied; no second review was done.
- **Reader suggestions are not findings.** Point 5 in each card is the reader's own idea. Claims in this report rest on the paper or code sections of the cards, or on the papers directly.
- **The pool.** Papers were found by four searchers on arXiv and rated by two models from abstracts. Blog posts and industry write-ups are out. Batch 2 was the next 10 by rank, and 3 papers in batch 1 were added by hand.
- **Code was read, not run.** It is the current default branch, not the commit from when the paper appeared. MemGPT's is the `archive` branch of Letta, its successor. HippoRAG's repo is HippoRAG 2 (the follow-up), A-MEM's is the library rather than the experiments, and Mem0's README scores are for a newer algorithm than the paper's. Four papers have no code.
- **Same team on both sides.** This was written by an agent working in the Goals repo for its owner. Goals went through the same card method and quote check, but the conclusions are not independent.
- **Papers report their own results.** Gains quoted here are what the authors state, on their benchmarks.
- **A snapshot.** Papers and repos as of 2026-11-19.

## Papers read

29 papers, in the order they were ranked. Each links to its card. Batch 2 is the next 10 by rank.

| Rank | Paper | Year | Theme | Code | Card |
|---|---|---|---|---|---|
| 1 | [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) | 2023 | T3 | read | [2303.11366](cards/2303.11366.md) |
| 2 | [Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291) | 2023 | T3 | read | [2305.16291](cards/2305.16291.md) |
| 3 | [Agent Workflow Memory](https://arxiv.org/abs/2409.07429) | 2024 | T4 | read | [2409.07429](cards/2409.07429.md) |
| 4 | [ReasoningBank: Scaling Agent Self-Evolving with Reasoning Memory](https://arxiv.org/abs/2509.25140) | 2025 | T4 | read | [2509.25140](cards/2509.25140.md) |
| 5 | [Agentic Context Engineering: Evolving Contexts for Self-Improving Language Mod](https://arxiv.org/abs/2510.04618) | 2025 | T2 | read | [2510.04618](cards/2510.04618.md) |
| 6 | [ExpeL: LLM Agents Are Experiential Learners](https://arxiv.org/abs/2308.10144) | 2023 | T4 | read | [2308.10144](cards/2308.10144.md) |
| 7 | [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) | 2023 | T1 | read | [2310.08560](cards/2310.08560.md) |
| 8 | [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413) | 2025 | T1 | read | [2504.19413](cards/2504.19413.md) |
| 9 | [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) | 2023 | T1 | read | [2304.03442](cards/2304.03442.md) |
| 10 | [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) | 2025 | T1 | read | [2502.12110](cards/2502.12110.md) |
| 11 | [A Survey on the Memory Mechanism of Large Language Model based Agents](https://arxiv.org/abs/2404.13501) | 2024 | T1 | none | [2404.13501](cards/2404.13501.md) |
| 12 | [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956) | 2025 | T1 | read | [2501.13956](cards/2501.13956.md) |
| 13 | [Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory](https://arxiv.org/abs/2504.07952) | 2025 | T2 | read | [2504.07952](cards/2504.07952.md) |
| 14 | [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457) | 2025 | T4 | read | [2507.19457](cards/2507.19457.md) |
| 15 | [Memory in the Age of AI Agents](https://arxiv.org/abs/2512.13564) (batch 2) | 2025 | T1 | none | [2512.13564](cards/2512.13564.md) |
| 16 | [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172) | 2023 | T2 | read | [2307.03172](cards/2307.03172.md) |
| 17 | [ACON: Optimizing Context Compression for Long-horizon LLM Agents](https://arxiv.org/abs/2510.00615) (batch 2) | 2025 | T2 | read | [2510.00615](cards/2510.00615.md) |
| 18 | [MemoryBank: Enhancing Large Language Models with Long-Term Memory](https://arxiv.org/abs/2305.10250) (batch 2) | 2023 | T1 | read | [2305.10250](cards/2305.10250.md) |
| 19 | [HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Model](https://arxiv.org/abs/2405.14831) (batch 2) | 2024 | T1 | read | [2405.14831](cards/2405.14831.md) |
| 20 | [Memory OS of AI Agent](https://arxiv.org/abs/2506.06326) (batch 2) | 2025 | T1 | read | [2506.06326](cards/2506.06326.md) |
| 21 | [Memento: Fine-tuning LLM Agents without Fine-tuning LLMs](https://arxiv.org/abs/2508.16153) (batch 2) | 2025 | T4 | read | [2508.16153](cards/2508.16153.md) |
| 22 | [ReSum: Unlocking Long-Horizon Search Intelligence via Context Summarization](https://arxiv.org/abs/2509.13313) (batch 2) | 2025 | T2 | none | [2509.13313](cards/2509.13313.md) |
| 23 | [EverMemOS: A Self-Organizing Memory Operating System for Structured Long-Horiz](https://arxiv.org/abs/2601.02163) (batch 2) | 2026 | T1 | read | [2601.02163](cards/2601.02163.md) |
| 24 | [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) | 2022 | T3 | read | [2210.03629](cards/2210.03629.md) |
| 25 | [Recursive Language Models](https://arxiv.org/abs/2512.24601) (batch 2) | 2025 | T2 | read | [2512.24601](cards/2512.24601.md) |
| 26 | [Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents](https://arxiv.org/abs/2505.22954) (batch 2) | 2025 | T4 | read | [2505.22954](cards/2505.22954.md) |
| 31 | [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793) (hand pick) | 2024 | T3 | read | [2405.15793](cards/2405.15793.md) |
| 33 | [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657) (hand pick) | 2025 | T3 | read | [2503.13657](cards/2503.13657.md) |
| 64 | [Measuring AI Ability to Complete Long Software Tasks](https://arxiv.org/abs/2503.14499) (hand pick) | 2025 | T3 | none | [2503.14499](cards/2503.14499.md) |

The Goals card is [cards/goals-self.md](cards/goals-self.md).
