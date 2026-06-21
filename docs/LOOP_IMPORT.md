# Importing Loops

Goals can import reusable loop definitions from a URL, local file, directory,
catalog JSON/YAML, existing `loop-design.json`, or builder command script.

## Claude Code

Use the plugin slash command:

```text
/goals:import https://signals.forwardfuture.ai/loop-library/
```

If the source has more than one loop, Claude Code asks which one to import. If
the loop has placeholders such as `[N]` or is missing a concrete first step,
objective, or stop condition, Claude Code asks those questions and reruns the
import with repeated `--answer KEY=value` flags.

## Terminal

```bash
goals loop import <source> --out .goals --no-prompt
goals loop check --out .goals --target-agent claude
goals loop activate --out .goals --agent claude
```

Use `--select <id-or-title>` when a catalog contains multiple loops. Use
`--answer KEY=value` for each required placeholder or readiness question. Add
`--force` only when replacing existing loop artifacts is intentional.

## What Gets Written

Import writes the normal loop artifacts:

- `.goals/loop-design.json` - the durable editable loop design.
- `.goals/goal-state.json` and `.goals/GOAL.md` - portable files any agent can read.
- `.goals/loop.html` - a standalone preview of the imported loop.

The saved design records provenance: original source, effective source when an
HTML page falls back to `catalog.json`, selected loop id, content hash, import
time, and warnings.

## Validation Profiles

Imported phases keep profile names such as `imported-loop`, `benchmark-loop`,
`browser-ux-loop`, `experiment-loop`, or custom profiles from
`registries/profiles.yml`.

Profiles expand reusable proof requirements during export, activation, and
`goals loop check`. They do not replace authored loop structure: a loop still
needs a real first step and a concrete stop condition from the imported content
or from your answers.
