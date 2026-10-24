## PR #56 - /upstream-reviews without committed project files

Plan
- Preferred: the fork's Action on its own basstler/upstream-reviews branch (push a request, run commits result.json, session replays it through the GraphQL reader). Fallbacks: attach the upstream and read REST; a Haiku helper session when the fork's same-named upstream can't be attached.

Done
- REST reader + models; setup step, check row; helper path (27 tests); Action path (31 tests); live on cram2 #777.
- main merged through v0.1.8 (#32 tag-only release): plugin_version replaced by basstler_branch_or_tag; input basstler_ref and flag --ref renamed to basstler_branch_or_tag / --branch-or-tag, no alias. 1084 tests pass.

Next
- Review on #56; owner confirms release:minor despite the input rename (or relabels release:major). Conflicts with #45 in setup files go to whichever lands second.
- User to delete basstler/push-probe and basstler/upstream-reviews on basstler.
