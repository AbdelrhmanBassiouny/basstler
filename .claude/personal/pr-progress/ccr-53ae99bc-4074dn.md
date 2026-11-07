### Plan
- Configuration.load falls back to the clone's own remote when no upstream is named
- maintenance skips upstream reads, promotion and synchronization when there is no upstream, and says so
- check-setup stack_upstream row and gathering doc: the stack pass runs with no upstream
- Catch-up stays merge, with rebase on label (confirmed with the owner)
### Done
- Bootstrap: branch, draft PR #157, item recorded in progress
### Next
- Failing tests for board, restack and stack configuration with no upstream
