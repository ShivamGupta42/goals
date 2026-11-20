# goals-self: How Goals handles each need
Clone folder: goals__self

1. Keep the context window small and healthy
   - Status: partial
   - Answer: SessionStart injects a short goal block (objective, phase, acceptance). Prompt hook injects nothing. Default next-step handoff is short; --full is longer. No compaction, trimming or summary logic (grepped compact, PreCompact, summariz, trim, truncat).
   - Evidence: [src/goals/agent_hooks.py:70] <<def session_start_payload(cwd: Path) -> str:>>

2. Remember what happened (episodic memory)
   - Status: has
   - Answer: Each change is appended to a per-goal events.jsonl and the goal snapshot is replayed from it. Verified checks store exit code and output hash. The log is local and git-excluded.
   - Evidence: [src/goals/storage.py:226] <<# Keep every existing line byte-for-byte. Re-serializing parsed events>>

3. Remember facts and who the user is (semantic memory)
   - Status: partial
   - Answer: Two Markdown files in ~/.goals/user: preferences.md (user-owned, steers behaviour) and observations.md (agent-appended choices, scoped to one goal). Covers user preferences only; no per-project preferences or project facts.
   - Evidence: "Preferences are global; observations are scoped." (docs/GOAL_EXECUTION_MEMORY.md)

4. Remember how to do things (procedural memory)
   - Status: partial
   - Answer: No automatic skill learning (no code writes skills from past goals). Skills are changed by hand after repeated friction. Friction notes persist in goals memory and sync across projects as sanitized suggestions; imported loop designs are reusable workflows.
   - Evidence: "Keep one-off observations in self-evolution memory or docs until they repeat." (skills/README.md)

5. Write only what is real (write gate)
   - Status: partial
   - Answer: Engine runs auto checks and sets ran/passed from exit codes; agents cannot set them. A manual or waived check with any non-empty rationale counts for acceptance criteria, and memory writes have no origin check.
   - Evidence: [src/goals/runtime.py:459] <<ran, passed = True, proc.returncode == 0>>
   - Evidence: [src/goals/gates.py:273] <<return bool(v.rationale.strip())>>
   - Evidence: [src/goals/user_memory.py:112] <<preference = Preference(area=_validate_area(area), text=_clean(text))>>

6. Update and forget
   - Status: partial
   - Answer: Event log is append-only; Discovery revise marks old pains and wants superseded. Preferences can be removed with goals user forget. Observations and friction memory only grow, with no decay or pruning (docs: prune by hand).
   - Evidence: [src/goals/user_memory.py:135] <<def forget_preference(target: str, *, purge: bool = False) -> list[str]:>>
   - Evidence: [src/goals/storage.py:559] <<- Recorded pain points and desired properties are superseded (they stop>>

7. Find the right memory at the right time (retrieval)
   - Status: partial
   - Answer: No search or ranking found (grepped search, retriev, embed, vector, bm25); only a skill lookup in the loop builder. Injection is fixed: goal block at session start; next --full adds 5 memory suggestions and the first 5 preferences in file order.
   - Evidence: [src/goals/user_memory.py:337] <<selected = preferences[:limit]>>
   - Evidence: [src/goals/mode_a.py:34] <<memory_suggestions = derive_memory_suggestions(load_memory(worktree, snapshot))[:5]>>

8. Catch loops and early stops
   - Status: partial
   - Answer: Opt-in Stop hook (GOALS_ENFORCE=1) blocks stopping while the phase has agent work, with two caps: 3 failed reviews (default) and a GOALS_MAX_TOKENS ceiling. Fails open. No repeated-action detection found (grepped stuck, stall, repeat, infinite).
   - Evidence: [src/goals/agent_hooks.py:122] <<if phase is not None and _circuit_breaker_tripped(phase):>>
   - Evidence: [src/goals/agent_hooks.py:188] <<usage = transcript_token_usage(transcript_path)>>

9. Measure whether the agent improves over time
   - Status: lacks
   - Answer: No cross-goal or cross-run metric, score or trend (grepped metric, score, trend, pass rate, success rate). Only a per-friction occurrence count in memory suggestions; the critique skill is a manual retrospective.
   - Evidence: [src/goals/memory.py:268] <<occurrences=len(entries),>>
