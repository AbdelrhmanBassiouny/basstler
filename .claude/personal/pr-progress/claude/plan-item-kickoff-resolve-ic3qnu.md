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
- Review round 1: `stack.py` functions moved onto classes (0c72f1d), and a test checks the
  `ConflictResponse` type (7a90808). The reviewer resolved both threads.
- Review round 2 (23dac4d): `stack.py` split into `stack_*` modules, strings are enums,
  abbreviations spelled out, `next_to_promote` removed. `release:minor` label set.
- Review round 3 (f459472): stack errors share a `StackError` base on `DataclassException`;
  the merge probe uses `match`.

## Next
- Open threads waiting on the reviewer: prose and URL strings as enums? (r4368761444); can
  the dead `ci` field go? (r4368763692); derive `in-review` from the upstream pull request
  instead of the label, as its own item or in this PR? (r4368773879).
- `ci` field: delete it, or type it `CheckOutcome` (r4368875261, same question as r4368763692).
