# How a goal run should go

Status: decisions locked. Nothing here is implemented. An earlier draft of this
file described a local model filter (Laya or SemIf) that scored every proposal.
That draft is replaced by the decisions below.

Goals already has a web page (`dashboard.html`), a phase loop that runs real
checks, and two memory files under `~/.goals/user/`: notes from one goal, and
standing rules that apply later only after you confirm them. This plan says
when those pieces are used, and adds two things Goals does not have: a required
opening talk, and a side panel in the terminal.

## 1. Opening talk

The opening talk stays on the big decisions. The result has to be clear before
any building. The agent suggests the way, shows simple references, and writes
so a person can follow.

The talk ends with a written list of what is in and what is out.

When someone will see a screen, Goals asks which picture to draw before it
draws:

- rough boxes and labels, or
- a picture that looks like the final app.

The agent draws that picture from the references. You say what is wrong. One
yes covers the list and the picture. Building starts after that yes.

A backend or script job has no picture. It ends with the written list, and
building starts after one yes on that list.

The screen, the server, and the connections to other systems are not designed
in this talk. They come after the yes.

## 2. Short jobs and long jobs

A long job is still fuzzy and splits into more than one piece.

A short job is one clear change. If the opening talk collapses a fuzzy idea
into one clear change, the job is short after that talk.

On a long job, progress is two counts:

- pieces agreed, against pieces done
- checks passed, against checks failed

The same mistake twice stops the job and asks you. It shows both times. It
does not try a third time until you answer.

The same mistake means the same check failed twice, or the same piece came
back twice for the same reason.

## 3. Memory

A new chat that picks up a long job reads four things first:

- the in/out list
- the two progress counts
- the open mistake, if the job is stopped
- your standing rules

A note from this job becomes a standing rule only when you say yes to that
exact rule. Goals asks. Goals does not say yes for you. The ask happens at the
end of the job: Goals shows the notes and asks yes or no on each one.

Notes from one goal stay notes until that yes. You can still edit the standing
rules by hand.

## 4. The side panel

One Goals view opens in a split beside Codex or Claude. The same view works
for both.

The panel shows only the short pack: the in/out list, the two counts, the open
mistake if the job is stopped, and the standing rules.

The web page stays. It keeps the full story. The panel does not replace it.

## Out of scope

- A local decision model, a fine-tune, and new model dependencies.
- A second chat with Goals inside the panel.
- A separate plugin for Claude and another for Codex.
- A keyword list that guesses whether a change is dangerous.
- A file stamp that proves which bytes a passing check covered.
- Designing the server or third-party connections during the opening talk.

## Done when

- A screen job cannot start building until the in/out list and the chosen
  picture exist, and you have said yes once.
- A backend or script job cannot start building until you have said yes to the
  in/out list.
- On a screen job, Goals asks “rough boxes or final-app picture?” before it
  draws.
- A job with one clear change does not get the long-job stop rule.
- A long job shows the two counts.
- The same check failing twice, or the same piece returning twice for the same
  reason, stops and asks, and does not try again until you answer.
- A new chat can continue a long job from the four-item pack alone.
- At the end of a job, Goals asks yes or no on each note. A note does not
  become a standing rule without your yes.
- The side panel and the web page can be open at the same time, and the panel
  shows only the short pack.
