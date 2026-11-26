#!/usr/bin/env python3
"""Print one table from the bench runs saved in bench/results/.

    uv run python bench/report.py
    uv run python bench/report.py --results some/other/folder

Runs are grouped by the code they tested, so a test goal is only ever compared
with itself. Every figure here is a [bench] result: a weak model, with no
person in the chat.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
ORDER = ["clear-goal", "vague-goal A", "vague-goal B", "cannot-pass", "planted-error",
         "new-session"]
HEADERS = ["test goal", "runs", "pass", "fail", "void", "time", "reported cost", "refused",
           "notes"]


def load_results(results_dir: Path) -> list[dict]:
    results = []
    for path in sorted(results_dir.glob("*/result.json")):
        result = json.loads(path.read_text())
        if "checks" in result:  # a run that was stopped before it was judged has none
            result["folder"] = path.parent.name
            results.append(result)
    return results


def tested_code(result: dict) -> tuple[str, str, str]:
    cli = result.get("goals_cli") or {}
    models = ", ".join(result.get("models_used") or []) or result.get("model_requested", "?")
    return (result.get("plugin_commit", "unknown"), cli.get("source_commit", "unknown"), models)


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def table(rows: list[list[str]]) -> str:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
             for row in rows]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines)


def render_group(results: list[dict]) -> str:
    plugin_commit, cli_commit, models = tested_code(results[0])
    first = results[0]
    cli = first.get("goals_cli") or {}
    out = [
        f"Code tested: plugin folder at {plugin_commit}, goals CLI {cli.get('version', '?')} "
        f"at {cli_commit}, {first.get('claude_code_version', 'Claude Code ?')}, model {models}",
    ]
    if cli.get("matches_plugin_dir") is not True:
        out.append(
            "WARNING: the `goals` CLI these runs called is not the code in the plugin folder.\n"
            f"  plugin folder: {first.get('plugin_dir')}\n"
            f"  goals CLI:     {cli.get('path')} (source: {cli.get('source')})\n"
            "  The commands, skills and hooks came from the plugin folder; the Python that\n"
            "  ran came from the CLI. Run the bench with `uv run` from the checkout under test."
        )
    if "+changes" in plugin_commit or "+changes" in cli_commit:
        out.append("Note: the tested code had changes that were not committed.")

    by_check: dict[str, list[tuple[dict, dict]]] = {}
    for result in results:
        for check in result["checks"]:
            by_check.setdefault(check["name"], []).append((result, check))
    names = [n for n in ORDER if n in by_check] + sorted(n for n in by_check if n not in ORDER)
    rows = [HEADERS]
    for name in names:
        pairs = by_check[name]
        verdicts = [check["verdict"] for _, check in pairs]
        counts: dict[str, int] = {}
        for _, check in pairs:
            for note in check["notes"]:
                counts[note] = counts.get(note, 0) + 1
        notes = "; ".join(f"{note} {n}/{len(pairs)}" for note, n in counts.items())
        if name.endswith(" B"):  # the same runs as part A: do not show their cost twice
            usage = ["(same runs)", "", ""]
        else:
            seconds = [result.get("seconds") or 0 for result, _ in pairs]
            cost = [result.get("cost_usd") or 0 for result, _ in pairs]
            refused = [len(result.get("refused") or []) for result, _ in pairs]
            usage = [f"avg {average(seconds):.0f} s", f"avg ${average(cost):.3f}",
                     f"avg {average(refused):.1f}"]
        rows.append([name, str(len(pairs)), str(verdicts.count("pass")),
                     str(verdicts.count("fail")), str(verdicts.count("void")), *usage, notes])
    out.append(table(rows))
    total = sum(result.get("cost_usd") or 0 for result in results)
    out.append(f"{len(results)} runs, ${total:.2f} reported cost in total.")

    to_read = [(result, check) for result in results for check in result["checks"]
               if check["verdict"] != "pass"]
    if to_read:
        out.append("Read each of these before counting it:")
        for result, check in to_read:
            reasons = "; ".join(check["reasons"])
            out.append(f"  {check['verdict']}  {check['name']}  {result['folder']}: {reasons}")
    return "\n".join(out)


def render(results: list[dict]) -> str:
    if not results:
        return "No saved runs. Run: uv run python bench/run.py --all --runs 3"
    groups: dict[tuple, list[dict]] = {}
    for result in results:
        groups.setdefault(tested_code(result), []).append(result)
    parts = [render_group(group) for group in groups.values()]
    parts.append("[bench] A weak model with no person in the chat. Compare a test goal only "
                 "with itself, before and after one change.")
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--results", type=Path, default=RESULTS, help="folder of saved runs")
    args = parser.parse_args(argv)
    print(render(load_results(args.results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
