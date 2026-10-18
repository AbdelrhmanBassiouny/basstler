basstler#7: tracking PR for basstler-open-pull-request-carryover (no code; close once settled).

Plan
- Carry 15 branches: merge main in (parents before children), run tests, push, open a draft PR quoting the original CRAM PR's unresolved threads, and set the item's branch/pull_request_number/repository in the moved plans.
- Retire 9 (CRAM #260 #282 #284 #285 #291 #293 #482 #514 #207): open an issue each, point the plan item at it, then delete the branch. Session git deletes may 403; if they do, hand the user the commands.

Done
- Bootstrapped: draft PR #7, manifest open/record, user confirmed the retire list.

Next
- src-era branches first (505 504 503 508 492), then the flat-package ones (420 424 430 253 280 277), then the integration stack (154 211 281 437).
