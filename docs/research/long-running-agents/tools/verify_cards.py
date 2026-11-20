"""Check paper cards: every paper quote is in the paper text, every code snippet is in the file.

Usage: python -I verify_cards.py CARDS_DIR PAPERS_DIR CODE_DIR

Card conventions (each card is CARDS_DIR/<arxiv_id>.md):
  paper quote:  "words copied from the paper" (4+ words, in double quotes)
  code quote:   [path/in/repo.py:123] <<one line copied from that file>>
  repo line:    Repo: https://github.com/owner/repo   (clone is CODE_DIR/owner__repo)
Paper quotes are compared on letters and digits only (PDF text breaks words and hyphens).
Code snippets must appear in the named file (whitespace collapsed) and the file must exist.
Exits 1 if anything is not found.
"""

import re
import sys
from pathlib import Path

PAPER_QUOTE = re.compile(r'["“]([^"“”\n]{12,}?)["”]')
CODE_QUOTE = re.compile(r"\[([^\]\n:]+):(\d+)(?:-\d+)?\]\s*<<(.+?)>>")
CLONE_LINE = re.compile(r"Clone folder:\s*(\S+)")
REPO_LINE = re.compile(r"Repo:\s*https?://github\.com/([^/\s]+)/([^/\s#?)]+)")
MIN_WORDS = 4


def alnum(text: str) -> str:
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("­", "")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    cards_dir, papers_dir, code_dir = (Path(p) for p in sys.argv[1:4])
    cards = sorted(cards_dir.glob("*.md"))
    paper_total = paper_found = code_total = code_found = 0
    problems: list[str] = []
    for card in cards:
        arxiv_id = card.stem
        body = card.read_text()
        paper_file = papers_dir / arxiv_id / "paper.txt"
        source = alnum(paper_file.read_text()) if paper_file.exists() else ""
        if not source:
            problems.append(f"{arxiv_id}: no paper text found")
        prose = re.sub(r"<<.+?>>", lambda m: " " * len(m.group(0)), body)
        for match in PAPER_QUOTE.finditer(prose):
            quote = match.group(1)
            if len(quote.split()) < MIN_WORDS:
                continue
            paper_total += 1
            if alnum(quote) and alnum(quote) in source:
                paper_found += 1
            else:
                problems.append(f"{arxiv_id}: PAPER QUOTE NOT FOUND: {quote[:90]}")
        repo = REPO_LINE.search(body)
        override = CLONE_LINE.search(body)
        clone = (
            code_dir / override.group(1)
            if override
            else (
                code_dir / f"{repo.group(1)}__{repo.group(2).removesuffix('.git')}"
                if repo
                else None
            )
        )
        for match in CODE_QUOTE.finditer(body):
            rel, _line, snippet = match.groups()
            code_total += 1
            if clone is None or not clone.exists():
                problems.append(f"{arxiv_id}: code quote but no cloned repo for {rel}")
                continue
            target = (clone / rel).resolve()
            if clone.resolve() not in target.parents or not target.is_file():
                problems.append(f"{arxiv_id}: FILE NOT FOUND in repo: {rel}")
                continue
            if squash(snippet) in squash(target.read_text(errors="replace")):
                code_found += 1
            else:
                problems.append(f"{arxiv_id}: CODE SNIPPET NOT FOUND in {rel}: {snippet[:80]}")
    print(
        f"cards={len(cards)} paper_quotes={paper_total} found={paper_found} | "
        f"code_snippets={code_total} found={code_found} | problems={len(problems)}"
    )
    for problem in problems:
        print("  ", problem)
    return 1 if problems or paper_total == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
