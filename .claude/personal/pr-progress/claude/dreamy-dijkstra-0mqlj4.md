PR #82 (draft, bug, patch): collapse only restack-made merges.
Plan:
- Mark restack merges with Restacked-parent + Restacked-parent-commit trailers; collapse only those whose commit trailer is the merged-in parent
- Count merges as superseded against parent + own line (reparents)
- Fall back to shallower start points before the tip
Done:
- All three, with failing-first tests; docs and skill updated; draft PR opened
- SHA binding (review thread on CommitTrailer) pushed as 2181043, thread resolved
Next:
- Wait for review/CI prompts from the user
