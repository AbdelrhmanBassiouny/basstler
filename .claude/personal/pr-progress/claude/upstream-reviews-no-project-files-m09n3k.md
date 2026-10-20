## PR #56 - /upstream-reviews without committed project files

Plan
- Preferred: the fork's Action on its own basstler/upstream-reviews branch (push a request, run commits result.json, session replays it through the GraphQL reader). Fallbacks: attach the upstream and read REST; a Haiku helper session when the fork's same-named upstream can't be attached.

Done
- REST reader + models; setup step, check row; 0.2.0; main merged (0.1.6).
- Helper path, 27 tests; live on cram2 #777.
- Action path (upstream_reviews_action, reusable upstream-reviews-action.yml, setup_steps install-upstream-reviews-action, upstream_reviews_action check row, enable-Actions step), 31 tests; live on cram2 #777 from the real fork and via basstler as fork, both identical to a direct read.

Next
- Review on #56 (conflicts with #45 in setup files go to whichever lands second). User to delete basstler/push-probe and basstler/upstream-reviews on basstler.
