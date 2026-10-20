## PR #56 - /upstream-reviews without committed project files

Plan
- Session attaches the upstream (add_repo push) and reads it over REST; GraphQL stays for runners. Upstream in personal stack.toml via `setup_steps configure-upstream`, checked by `stack_upstream` (`--require-upstream`).

Done
- REST reader + models + equivalence test; skill rewritten; dispatch workflow and reviews_repository removed; verified live on cram2 #773.
- Setup step, check row, skill steps; 0.2.0 (`release:minor`); description and plan notes current.

Next
- Review on #56 (conflicts with #45 in setup files go to whichever lands second).
