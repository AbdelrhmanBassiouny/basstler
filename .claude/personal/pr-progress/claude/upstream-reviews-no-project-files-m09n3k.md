## PR #56 - /upstream-reviews without committed project files

Plan
- Session attaches the upstream and reads REST; GraphQL for runners/terminals. When the fork's same-named upstream can't be attached, a Haiku helper session runs the inline fetch program; report replays it from this session's transcript, then archives the helper.

Done
- REST reader + models; setup step, check row; 0.2.0; main merged (0.1.6).
- Helper path (upstream_reviews_helper/_fetch), 27 tests; verified live on cram2 #777 by branch, no user input.

Next
- Review on #56 (conflicts with #45 in setup files go to whichever lands second).
