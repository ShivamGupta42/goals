# How Goals works — architecture

Four diagrams that explain Goals to a newcomer. Every node maps to a real module
in `src/goals/`, a real `goals` command, or a real file in `registries/` /
`.claude-plugin/`. GitHub renders Mermaid natively, so these display inline.

> Honest line: **Goals runs the workflow; your AI does the work.** The agent
> executes each step; Goals keeps the plan, the decisions, and the proof.

---

## 1. System architecture (what's in the box)

A small Python CLI + a Claude Code / Codex plugin, sitting over plain files you
own. No server, no database.

```mermaid
---
config:
  theme: default
---
flowchart TB
    user([You — plain English goal])
    agent([Your AI agent<br/>Claude Code / Codex])

    subgraph plugin["Plugin surface (.claude-plugin/, commands/, hooks/, skills/)"]
        cmds["/goals:create · /goals:next<br>/goals:check · /goals:diagram"]
        sk["bundled skills/<br>SKILL.md files"]
    end

    subgraph cli["Goals CLI (src/goals/, entrypoint cli.py)"]
        runtime["runtime.py<br/>orchestration"]
        gates["gates.py + rubric.py<br/>executed-proof gate"]
        skill["skill_discovery.py<br/>skill_capabilities.py"]
        cap["capabilities.py<br/>capability-gap (Trust V1)"]
        journey["journey.py + decisions.py<br/>building journey (PACERS)"]
        port["portability.py<br/>cross-agent spec"]
        merge["merge_readiness.py<br/>git_ops.py"]
        dash["dashboard.py<br/>human-readable HTML"]
    end

    subgraph state["File-backed state (in your repo, you own it)"]
        goalstate[".goals/GOAL.md<br/>.goals/goal-state.json"]
        wf[".agent-workflow/goals/&lt;slug&gt;/<br/>evidence-*.json · events.jsonl<br/>dashboard.html · architecture.md"]
    end

    subgraph reg["registries/ (declarative config)"]
        regfiles["profiles · permissions<br/>adapters · gates · agents"]
    end

    user --> agent --> plugin --> cli
    user -.terminal.-> cli
    cli --> state
    cli --> reg
    skill --> sk
    dash --> goalstate
    runtime --> gates & skill & cap & journey & port & merge & dash
```

**Why it's shaped this way:** state lives in *your* repo as plain files, so a goal
survives `/clear`, a new session, or even a different agent. The registries make
behaviour declarative; the plugin is just a thin command surface over the CLI.

---

## 2. The goal lifecycle (start → done)

The loop every goal runs through. PACERS (Pause, Assess, Choose, Execute, Review,
Systemize) is recorded as a readable *building journey*; a phase is accepted only
after its checks **actually run**.

```mermaid
---
config:
  theme: default
---
flowchart TD
    start["goals start 'a goal'<br/>isolated worktree on main"] --> assess

    subgraph assess["Assess — PACERS (goals assess)"]
        bd["breakdown: problem → sub-problems"]
        asm["assumptions: the load-bearing ones"]
        bd --> asm
    end

    assess --> loop

    subgraph loop["Phase loop (repeat per phase)"]
        direction TB
        nextp["goals next → current phase + acceptance"]
        build["agent builds ONLY this phase"]
        ev["goals phase evidence<br/>runnable checks per criterion + assumption"]
        verify{"goals phase verify<br/>checks executed, real exit codes"}
        review{"goals phase review<br/>proof, not narration"}
        accept["goals phase accept"]
        nextp --> build --> ev --> verify
        verify -- "any check fails" --> build
        verify -- "all pass" --> review
        review -- "fail" --> build
        review -- "pass" --> accept
        accept --> nextp
    end

    loop --> finish["goals finish<br/>closeout + portable spec"]

    brief["goals check / goals brief<br/>plain-language status"] -.reads.-> loop
    dash["goals view → dashboard.html"] -.renders.-> loop
```

**The differentiator:** between `verify` and `accept`, the engine *runs* your
checks and records real exit codes (`gates.py`). A passing result can't be
asserted by the agent — it has to be earned.

A real completed goal's dashboard, showing the building journey:

![Goal dashboard](assets/dashboard-hero.png)

---

## 3. Skill-first discovery + capability-gap (Trust V1)

Before working, Goals checks it actually *has* the skills/tools a goal needs.

```mermaid
---
config:
  theme: default
---
flowchart LR
    goal[Goal + phase text] --> infer["capabilities.py<br/>infer needs (e.g. browser/UI)"]
    subgraph disc["skill_discovery.py"]
        scan["scan SKILL.md files"]
        roots["agent skill roots<br/>+ bundled skills/ (in wheel)"]
        scan --> roots
    end
    infer --> compare{"compare needs<br/>vs discovered skills"}
    disc --> compare
    compare -- missing --> gapM["report: missing skill"]
    compare -- "bundled, not installed" --> gapB["report: install it"]
    compare -- "wrong agent" --> gapW["report: wrong agent"]
    compare -- "all covered" --> ok["proceed"]
    gapM & gapB & gapW --> surface["surfaced in:<br/>goals issues · brief · check<br/>dashboard · next --full"]
```

**Why it matters:** an agent that starts a UI task with no browser skill wastes a
session. Goals catches the gap up front and tells you, in plain language, what's
missing (`goals capability check`).

---

## 4. The portability layer (why a goal outlives one session)

Native agents own the fast inner loop but their goal/task primitives are
vendor-locked and short-lived. Goals owns the durable, portable state.

```mermaid
---
config:
  theme: default
---
flowchart TB
    subgraph native["Native agent (vendor-locked, short-lived)"]
        loopN["inner loop: edit, run, test"]
    end
    subgraph goals["Goals (durable, portable, in your repo)"]
        spec[".goals/ portable spec<br/>goals export"]
        emit["goals emit → native /goal stop-condition"]
        ctx["goals context sync<br/>AGENTS.md / CLAUDE.md blocks"]
        adapt["adapters.py + registries/adapters.yml<br/>claude · codex"]
    end
    loopN <-->|"goals next handoff"| adapt
    spec --> emit --> loopN
    ctx --> native
    spec -.survives /clear, new session, agent switch.-> spec
```

**The wedge in one sentence:** your agent forgets the plan on `/clear`; Goals
keeps the goal, the decisions, and the evidence in files you own — and any agent
can pick the goal back up.

---

## Regenerating the diagrams

The Mermaid blocks above are the source of truth. To re-render the static SVGs in
[`assets/`](assets/):

```bash
npx -y @mermaid-js/mermaid-cli -i docs/architecture.md -o docs/assets/architecture.svg
# produces docs/assets/architecture-1.svg … architecture-4.svg (one per diagram)
```

Every component above is verifiable against the codebase: each named module
exists in `src/goals/`, each `goals` command exists in `goals --help`, and each
registry file exists in `registries/`.
