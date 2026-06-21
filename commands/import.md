---
description: Import an external loop definition or catalog into Goals.
argument-hint: <source> [--select <id|slug|title>] [--answer KEY=value] [--force]
---

Import a loop definition into this repo's Goals loop files.

1. Treat **$ARGUMENTS** as the loop source plus optional `goals loop import`
   flags. If no source was provided, ask the user for a URL, local file,
   directory, builder script, catalog JSON/YAML, or pasted loop definition.
2. Set `OUT_DIR` to the value after `--out` when `$ARGUMENTS` includes one. If
   the user did not supply `--out`, run
   `goals loop import $ARGUMENTS --out .goals --no-prompt` and use that same
   output directory as `OUT_DIR`. If they did supply `--out`, run
   `goals loop import $ARGUMENTS --no-prompt`. Do not add `--force` unless the
   user explicitly asks to replace existing loop artifacts.
3. If import fails because the source contains multiple loops, ask which loop to
   import and rerun with `--select <id-or-title>`.
4. If import reports missing required details, ask the user concise questions for
   those placeholders and rerun with repeated `--answer KEY=value`.
5. Run `goals loop check --out "$OUT_DIR" --target-agent claude`. If it reports
   only safe fixes, run
   `goals loop check --out "$OUT_DIR" --target-agent claude --fix` and then check
   again. Stop and summarize any blocking issues.
6. Summarize the imported loop, selected candidate, answers, saved files, source
   hash, and validation result. If the user wants to start from the imported
   loop immediately, run `goals loop activate --out "$OUT_DIR" --agent claude`.

Examples:

```bash
/goals:import https://signals.forwardfuture.ai/loop-library/ --select quality-streak-loop --answer N=3
/goals:import ./catalog.json --select my-loop --answer N=5
```
