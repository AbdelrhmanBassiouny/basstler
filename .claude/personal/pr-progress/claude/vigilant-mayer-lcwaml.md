Plan
- Every plan's merged items recorded at session start; one item per branch (PR #187, draft).

Done
- Merge-time workflow dropped; session start runs `merged_items every-plan`.
- One item per branch enforced; `domain-models` cleaned; BranchReport simplified (#201 merged in).
- a845f0a: merged-items code moved out of `__init__` into `plan_items.py` and `every_plan.py`; thread resolved.

Next
- Owner decides two open threads: push_attempts declared by the edit or the caller; non-mapping plan.yaml skipped or raised.
- Read CI on a845f0a; restack onto main 4d2af79 when asked.
