# Skill Evolution

Goals should learn from repeated workflow friction without growing a new public
command surface. Self-evolution memory captures the observation; skills carry
the reusable agent behavior.

## Path

1. Record friction with `goals memory record` or let phase evidence/reviews feed
   self-evolution memory.
2. Review repeated or high-severity patterns with `goals memory suggest` and
   `goals loop improve`.
3. If the lesson changes how future agents should act, update an existing skill
   or add a new bundled skill.
4. Validate skill metadata, command references, installability, and release
   packaging before merge.

## Promotion Criteria

Promote a lesson into a skill when at least one of these is true:

- The same agent mistake repeats across phases or projects.
- A high-severity failure would be expensive to repeat.
- The fix is procedural: another agent should follow a different workflow next
  time.
- The lesson requires reusable scripts, references, or assets.

Do not promote a lesson into a skill when it is a one-off project note, private
user preference, or simple documentation correction.

## Skill Update Rules

- Prefer editing the narrowest existing skill that owns the behavior.
- Keep the frontmatter `description` focused on trigger conditions.
- Keep detailed reference material in `references/` and mention when to read it
  from `SKILL.md`.
- Keep private memory private. Only publish sanitized, reusable behavior.

## Validation

- `tests/test_skill_hygiene.py` checks frontmatter and command references.
- `tests/test_loop_check.py` checks that bundled-only skills do not silently pass
  loop validation before installation.
- The wheel inventory smoke check verifies source `skills/*` are packaged as
  `goals/bundled_skills/*`.
