# Loop Engineering Needs More Than a Loop

*Long-running agent loops are not useful because they keep going. They are useful when you can trust what happened while you were away.*

Loop engineering is becoming popular.

It feels like the next step in working with AI coding agents. Once you have seen an agent keep working across several turns, make edits, run tests, inspect failures, and continue without you typing every instruction, it is hard to go back to one-shot prompting.

I get the appeal. I have been running `/loop` in Claude Code on personal projects for months.

It is powerful.

But the more loops I run, the more one thing stands out:

**A loop needs more than a prompt.**

The loop itself is only the motion. It can keep going. It can retry. It can inspect output and make another attempt. That is useful, but it is not enough.

If the loop does not know what counts as done, it may keep improving the wrong thing.

If it does not run proof, it may narrate success instead of earning it.

If its state only lives in the current chat, you lose the thread when you clear context, start a new session, or switch tools.

If its decisions are explained as technical trivia, you may approve something without understanding what it means for the goal.

The hard part is no longer just making an agent run longer.

The hard part is making longer runs something you can trust, verify, fix, and continue.

That is what I am building with **Goals**.

## The first loop failure I kept seeing

Early on, I would let a loop run in short bursts. Five minutes here. Another five minutes there.

Sometimes I came back to progress. Sometimes I came back to a strange kind of almost-progress.

The agent had touched files. It had updated tests. It had cleaned something up. The transcript looked busy.

But the feature I had asked for still was not built.

One pattern showed up more than once: the loop kept polishing the test cases. It improved names, tightened assertions, adjusted setup, and made the test file look better. None of that was useless. It just was not the actual work.

The agent had found a locally rewarding task.

It was easy to improve.

It was nearby.

It felt like progress.

That is the trap with loops. They are very good at continuing. Continuing is not the same as staying accountable to the original goal.

I had not given the loop a strong enough definition of done. I had not made it carry the goal through every step. I had not required executable proof before accepting work. And I had not given myself a durable record of what it decided while I was not watching.

A loop without those things is just horsepower.

It can still move in the wrong direction.

## What a useful loop needs

A useful agent loop needs at least five things.

First, it needs a plan it can carry across sessions.

Not a vague instruction like "keep working." A real plan. Current phase. Next step. What has already happened. What is blocked. What evidence exists. What still needs a human answer.

Second, it needs proof that actually runs.

The agent saying "done" should not be enough. A step should pass only when the relevant checks execute. That might be tests, a build, a lint run, a generated screenshot, a dashboard check, or some other proof tied to the work.

Third, it needs failure to become repair.

When a check fails, the loop should not shrug and move on because the failure looks inconvenient. It should inspect the failure, connect it back to the goal, and turn it into the next repair.

Fourth, it needs memory you own.

If everything important lives only in the chat, the workflow is fragile. `/clear` should not erase the goal. A new session should not lose the plan. Switching from Claude Code to Codex should not mean starting from zero.

Fifth, it needs decisions explained in goal-language.

This one matters more than it sounds.

Coding agents often surface decisions as technical options: use SQLite or Postgres, add a queue or keep it synchronous, split a module or leave it inline, introduce a new dependency or write the small function yourself.

Those are technical choices. But the human usually needs a different explanation.

What does this choice mean for the goal?

What risk does it create?

Can we reverse it later?

Does it speed up the current task while making the future harder?

Does it preserve the thing the user actually asked for?

For example, "SQLite vs Postgres" is not just a database preference. If the goal is a personal local tool, SQLite may be simpler, faster, and easy to reverse. If the goal is a multi-user app with shared accounts and payments, Postgres may fit the goal better even if it adds setup cost.

The explanation should not be:

- SQLite is embedded.
- Postgres is client-server.
- Postgres supports more concurrent writes.

That may be true, but it is not enough.

The useful explanation is:

- For your current goal, SQLite keeps the first version simpler.
- The risk is that we may need a migration if this becomes multi-user.
- The choice is reversible if we keep the data layer small.
- My recommendation is SQLite now, with a clear boundary so we can switch later.

That is the kind of decision an agent should bring to a human.

Not specs in isolation.

Meaning, tradeoff, risk, and reversibility in light of the goal.

## Where Goals fits

Goals is a small CLI and plugin for Claude Code and Codex.

It is not another coding agent. The agent still does the work. Goals is the workflow layer around the agent: the plan, state, checks, decisions, evidence, dashboard, and recovery path.

You start with a plain-English goal:

```bash
goals start "add login and payments to my app"
```

Goals turns that into tracked phases. The agent can ask for the next step:

```bash
goals next
```

You can check where things stand:

```bash
goals check
```

And you can open a readable dashboard:

```bash
goals view
```

The important part is where the state lives.

Goals saves the work done in your loops in files you own: the goal, current phase, decisions, evidence, failed checks, and history. That means the loop has something stable to be accountable to.

Not just "what was in the model's context."

Not just "what the transcript seems to imply."

Actual files.

Readable state.

Proof you can inspect.

## Trust the loop

Trust does not mean "believe the agent."

Trust means you can inspect the work without replaying the whole conversation in your head.

If the agent made a decision, the decision should be recorded. If it accepted a step, the proof should be there. If it hit a failure, the failure should not disappear into the transcript.

This is especially important for long-running loops because your attention will not cover every minute of the run.

That is the point of using a loop.

You want to step away.

But stepping away only works if there is a reliable way to come back.

## Verify before done

One of my strongest rules for Goals is simple:

**A step does not pass because the agent says it is done. It passes when the proof for that step runs.**

This sounds obvious until you watch agents work.

They can be very convincing. They summarize well. They often know what success should look like. But a good summary is not the same as a passing check.

For coding work, proof might be a test run. For a UI change, it might include a screenshot. For a documentation update, it might include a stale-command scan. For a packaging task, it might include a build.

The kind of proof changes with the task.

The rule does not.

Done has to be earned.

## Fix what breaks

Failed checks are not interruptions. They are information.

A loop should treat them that way.

If a test fails, the next move is not "keep going somewhere else." It is to understand why the proof failed and decide whether the failure changes the next step.

Sometimes the fix is direct: update the implementation.

Sometimes the failure reveals the goal was underspecified.

Sometimes it exposes a decision that should go back to the human.

Sometimes it shows the agent was optimizing for a simpler task than the one you actually asked for.

This is why I care about making failures visible. A failed check should point to the next repair, not become a vague retry loop.

Otherwise, looping just makes confusion repeat faster.

## Resume without losing the thread

The best loop is not always one uninterrupted run.

Real work is messier than that.

You clear context. You restart the tool. You change your mind. You switch agents. You realize the goal needs a different next step. You come back tomorrow.

If the goal only lives in the current chat, all of that hurts.

Goals is built around portable files so the work can survive those breaks. The plan, proof, decisions, and history are not trapped in one model's context window.

That matters for Claude Code.

It matters for Codex.

It matters for whatever agent comes next.

The workflow should outlive the session.

## Improve the loop itself

One more thing becomes obvious after you run enough loops: the same friction repeats.

The agent forgets a check.

The agent asks a decision too late.

The agent does not explain the risk clearly enough.

The agent keeps trying the same repair after a failure.

When that happens, the answer should not be to hand-audit every future run. The workflow itself should improve.

That is the idea behind `goals loop`: use repeated friction to improve how the loop behaves. If the problem is a missing check, add the check. If the problem is a bad decision rule, tighten the rule. If the problem is unclear guidance, update the skill.

The goal is not to babysit the loop forever.

The goal is to make the loop easier to trust next time.

## A small way to try this

If you are experimenting with loop engineering, try this on one real task.

Pick something small enough to finish, but large enough that an agent can drift. A UI feature with tests. A cleanup with a clear definition of done. A script that needs docs and verification. A bug where the first fix might not be the right fix.

Before you run the loop, write down four things:

- What does done mean?
- What proof should run?
- What decisions should come back to you?
- What state would you need if you resumed tomorrow?

Then run the loop and look for the gaps.

Did it keep the goal in view?

Did it verify the right thing?

Did it explain decisions in terms of your goal?

Did failures become repairs?

Could you resume the work without rereading the whole transcript?

Those questions are the real test.

## The point

I do not think the interesting question is whether agents can run longer.

They can.

The interesting question is whether longer runs can become accountable.

Can you trust what happened while you were away?

Can you verify the work before accepting it?

Can a failed check become the next repair?

Can a technical decision be explained in terms of your goal instead of buried in specs?

Can you resume tomorrow without losing the thread?

That is the direction I want Goals to push toward.

The project is open source:

https://github.com/ShivamGupta42/goals

Try it on one real loop. If the workflow still feels hard to trust, I want to know where.

*Loop engineering is not about making agents move forever. It is about giving their motion something to be accountable to.*
