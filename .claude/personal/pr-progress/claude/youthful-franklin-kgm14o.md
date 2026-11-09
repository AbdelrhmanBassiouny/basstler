## Plan
- Fix #152: the plan site build reads private repositories through an optional PLAN_SITE_READ_TOKEN; publication checks every repository the build reads and says so before writing.

## Done
- Build secret, publication check, step text, corrections, skill docs; first review's four gaps (gap 3 is unreadable-repository-items).
- Second review (7e4f244): PlanManifest.from_yaml, Repository.settings_url, initial_branch in tests; four threads resolved. Merged main with #140 (3e6140b). Public-site warning on the read-access step (165748f); pushed.

## Next
- Owner's decision on two open threads: duplicates guard (no change made), and the classic token's breadth for several owners.
- CI at 165748f not yet read. PR stays draft.
