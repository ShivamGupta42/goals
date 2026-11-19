# Long-running agents: which papers matter, and how they were chosen

Snapshot: 2026-11-19. This folder holds the method and the data behind the paper reading.
The reading results come later, in `cards/` and the findings report.

Goal behind it: what AI agents that run for hours or days need (kinds of memory, context
handling), how they keep adapting over time, and how that compares with Goals, a small layer
that sits inside Claude Code and Codex.

## Steps and numbers

1. **Pool.** Four searchers, one per theme, looked for papers on arXiv.
   - T1 memory architectures (20 papers), T2 context engineering (20), T3 long-horizon agents and harnesses (12), T4 adapting over time (20).
   - 72 entries became **67 unique papers** after merging duplicates.
2. **Check.** `tools/validate_pool.py` looked up every id on arXiv and compared titles. 67 of 67 verified, 0 rejected.
3. **Reach.** `tools/citations.py` pulled citation counts from Semantic Scholar: 65 of 67 found.
4. **Rate.** Two independent raters (one Sonnet 5.5, one Haiku 5.5) scored every paper from its title and abstract. Their files are `rater-A.json` and `rater-B.json`. They did not see each other's scores or the citation counts.
5. **Rank and pick.** `tools/rank.py` applied the rubric below and picked 16: the top by score, with at least the 3 best papers per theme.
6. **Hand picks.** 3 more were added by hand (see below). That made **19 papers** in the first batch.
7. **Batch 2.** Because there was time left, the next 10 papers by rank were read as well (`ranking-batch2.json`). **29 papers are read in full.**
8. **Fetch.** `tools/fetch_papers.py` downloads each chosen PDF and clones its official code. 25 of the 29 have code (MemGPT's is the `archive` branch of Letta, its successor); 4 do not (two surveys, METR's measurement study, ReSum).
9. **Read.** One reader agent per paper wrote a card with a quote and a location for every point, plus a code card with real file and line citations. `tools/verify_cards.py` then looked up every quote in the paper text and every code snippet in its file: **115 of 115 paper quotes and 167 of 167 code snippets were found.** Cards are in `cards/`.

## The rubric (written before any rating)

Each part is 0 to 3. Score = 0.3 reach + 0.3 relevance + 0.2 evidence + 0.2 usefulness, shown out of 100.

| Part | Weight | What it measures | Where it comes from |
|---|---|---|---|
| Reach | 30% | Influence: citations per year, 200+ = 3, 50+ = 2, 10+ = 1, else 0. Papers under a year old get at least 1 | Semantic Scholar counts |
| Relevance | 30% | How directly it addresses memory, context handling or adapting for agents over long runs | Mean of 2 raters |
| Evidence | 20% | Benchmarks with baselines and ablations or real deployments, versus opinion | Mean of 2 raters |
| Usefulness | 20% | Can a harness like Goals build the idea with plain files, prompts or hooks, without training? Official code counts here | Mean of 2 raters |

The full table of all 67 papers is in [ranking.md](ranking.md). The same data is in `ranking.json`.

## The 3 hand picks

SWE-agent (rank 31), Why Do Multi-Agent LLM Systems Fail? (rank 33) and Measuring AI Ability to Complete Long Software Tasks (rank 64) were added by hand. The rubric rewards memory, context and adaptation ideas that Goals can reuse, so papers about the harness itself and about why long runs fail scored low on relevance and usefulness. They are the core of "long-running agents", so they are read anyway. The choice is flagged in `ranking.json` (`manual_pick`).

## Commands

- `uv run --with defusedxml python -I tools/validate_pool.py POOL_DIR OUT.json`
- `python -I tools/citations.py POOL.json OUT.json`
- `python -I tools/rank.py POOL.json RATER_A.json RATER_B.json OUT.json OUT.md 16`
- `uv run --with pypdf python -I tools/fetch_papers.py RANKING.json PAPERS_DIR CODE_DIR OUT.json`
- `python -I tools/verify_cards.py CARDS_DIR PAPERS_DIR CODE_DIR` (checks quotes and code snippets in the cards)

## Risks and limits

- **Model ratings, not expert ratings.** Two models scored from abstracts only. Averaging two lowers noise but does not make them experts. No picked paper had raters more than 1 point apart on any scale.
- **Citations favour old papers.** A paper under a year old gets a floor of 1 point. Two papers have no count at all.
- **Search was arXiv only, by four searchers.** Blog posts, industry write-ups and non-arXiv papers are not in the pool. The harness theme (T3) is the thinnest, with 12 papers.
- **Theme tags are rough.** A paper's first theme is the first pool it appeared in, so Reflexion and Voyager count under T3 although they are about adapting.
- **Official-code links came from the searchers.** They were checked by cloning. One link was stale (Reflexion, fixed by hand to `noahshinn/reflexion`). Zep's open-source core is Graphiti, and A-MEM has two repos, so the card says which one was read.
- **A paper and its code can differ.** The cards say where they do.
- **Rate limits.** arXiv and Semantic Scholar throttled the helpers and one script call. Results were retried, not skipped.
- **PDFs and code clones are not committed.** They sit in a temp folder. Re-create them with `tools/fetch_papers.py`.
