### Plan
- Configuration.load falls back to the clone's own remote when no upstream is named
- maintenance skips upstream reads and promotion when there is no upstream, and says so
- check-setup and the gathering doc: the stack pass runs with no upstream
### Done
- Fix and tests pushed (bbaa0efc); PR #157 description current, labelled bug
- Merge stays the catch-up rule (owner); old exit-11 test rewritten (owner-approved)
### Next
- CI on #157; owner review
