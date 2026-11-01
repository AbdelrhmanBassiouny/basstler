### Plan
- #111 (draft, no label): base `basstler.branch.Branch` shared by RemoteBranch and the stack's branch (renamed StackBranch); from #105's review.

### Done
- #105 merged; its Branch thread answered and resolved, pointing to #111.
- #111 opened (66d39ef); merged main in (d892907); 1871 tests pass.

### Next
- Wait on the owner's review of #111.
- From #105: two threads were left open (write() on the runner, run-listing type); run the publication command after release; store PLAN_SITE_TOKEN; close stack-board#7.
