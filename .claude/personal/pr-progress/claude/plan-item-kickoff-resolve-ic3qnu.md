Draft #15, continued here from CRAM #430.

## Plan
- Restack one branch's subtree: `Stack.branches_stacked_on`, `Stack.restack_plan(stacked_on=)`
  and `maintenance restack --stacked-on`, with collisions answered by
  `ConflictResponse.chosen_for` (`TellTheBranchOwner` / `LeaveItToTheCaller`).
- `propagating-a-fix.md` holds the parent-to-descendant judgement, linked from the
  resolve skill's `SKILL.md`.

## Done
- Merged main (2026-10-24): moved the test constants into main's `tests/constants/` split,
  and kept main's superseded-merge integration in `IntegrateParent`.
- Review: every module-level function in `stack.py` moved onto a class (0c72f1d).
- Review: added tests asserting which `ConflictResponse` type is chosen (7a90808).

## Next
- Thread r4368631657 is left open: confirm the reading (the response type) or say what
  was meant instead.
- Asked on the PR whether `Stack.next_to_promote`, which only tests call, can go.
- PR needs the `release:minor` label (not verified from this session).
