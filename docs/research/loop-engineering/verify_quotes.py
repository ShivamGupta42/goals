"""Check that every verbatim quote in cards.md really appears in its source text.

Usage: verify_quotes.py CARDS_MD README_CACHE_DIR GOALS_DIR

Each card starts with "### owner/repo". Its quotes are checked against
README_CACHE_DIR/owner__repo.md. The "### Goals" card is checked against the Goals files
under GOALS_DIR. Exits 1 if any quote of 4 words or more is not found.
"""

import re
import sys
from pathlib import Path

GOALS_FILES = [
    "README.md",
    "ROADMAP.md",
    "AGENTS.md",
    "docs/architecture.md",
    "docs/GOAL_EXECUTION_MEMORY.md",
]
MIN_WORDS = 4
QUOTE = re.compile(r'["“]([^"“”\n]{10,}?)["”]')


def norm(text: str) -> str:
    """Lowercase, drop markdown punctuation, unify quotes, collapse whitespace."""
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[`*_\\]", "", text)  # emphasis and code marks vanish: **a**. -> a.
    text = re.sub(r"[>#|\[\]()]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r" ([.,;:!?])", r"\1", text)


def source_text(heading: str, cache: Path, goals_dir: Path) -> str:
    if heading.strip().lower() == "goals":
        return "\n".join((goals_dir / name).read_text() for name in GOALS_FILES)
    repo = heading.split()[0]
    return (cache / (repo.replace("/", "__") + ".md")).read_text()


def segments(quote: str) -> list[str]:
    """Split a quote on ellipses so trimmed quotes are checked piece by piece."""
    parts = re.split(r"\.\.\.|…", quote)
    return [norm(p) for p in parts if len(norm(p).split()) >= MIN_WORDS]


def main() -> int:
    cards_path, cache, goals_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cards = re.split(r"^### ", cards_path.read_text(), flags=re.MULTILINE)[1:]
    total = found = 0
    missing: list[tuple[str, str]] = []
    for card in cards:
        heading, _, body = card.partition("\n")
        source = norm(source_text(heading, cache, goals_dir))
        for match in QUOTE.finditer(body):
            for seg in segments(match.group(1)):
                total += 1
                if seg in source:
                    found += 1
                else:
                    missing.append((heading.strip(), seg))
    print(f"cards={len(cards)} quotes={total} found={found} missing={len(missing)}")
    for heading, seg in missing:
        print(f"  NOT FOUND in {heading}: {seg[:100]}")
    return 1 if missing or total == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
