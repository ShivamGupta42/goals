from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZipFile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify built Goals wheels contain every source bundled skill."
    )
    parser.add_argument("wheel", nargs="+", type=Path, help="Wheel file(s) to inspect.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root containing the source skills directory.",
    )
    args = parser.parse_args(argv)

    expected = _source_skill_names(args.repo)
    failed = False
    for wheel in args.wheel:
        packaged = _wheel_skill_names(wheel)
        if packaged != expected:
            failed = True
            missing = sorted(expected - packaged)
            extra = sorted(packaged - expected)
            print(f"{wheel}: bundled skill inventory mismatch", file=sys.stderr)
            if missing:
                print(f"  missing: {', '.join(missing)}", file=sys.stderr)
            if extra:
                print(f"  extra: {', '.join(extra)}", file=sys.stderr)
        else:
            print(f"{wheel}: bundled skill inventory ok ({len(packaged)} skill(s))")
    return 1 if failed else 0


def _source_skill_names(repo: Path) -> set[str]:
    skills_dir = repo / "skills"
    return {
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }


def _wheel_skill_names(wheel: Path) -> set[str]:
    with ZipFile(wheel) as archive:
        return {
            parts[2]
            for name in archive.namelist()
            if (parts := name.split("/"))
            and len(parts) == 4
            and parts[0] == "goals"
            and parts[1] == "bundled_skills"
            and parts[3] == "SKILL.md"
        }


if __name__ == "__main__":
    raise SystemExit(main())
