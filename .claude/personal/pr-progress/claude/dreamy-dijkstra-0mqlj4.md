PR #82 (draft, bug, patch): collapse only restack-made merges.
Plan:
- Mark restack merges with a Restacked-parent trailer; collapse only those
- Count merges as superseded against parent + own line (reparents)
- Fall back to shallower start points before the tip
Done:
- All three, with failing-first tests; docs and skill updated; draft PR opened
Next:
- Review thread on CommitTrailer (trailer reliability): answered, open; awaiting your call on binding the merged SHA into the trailer
- Wait for review/CI prompts from the user
