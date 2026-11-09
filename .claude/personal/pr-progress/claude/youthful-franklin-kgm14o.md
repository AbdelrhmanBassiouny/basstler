## Plan
- Fix #152: the plan site build reads private repositories through an optional PLAN_SITE_READ_TOKEN; publication checks every repository the build reads and says so before writing.

## Done
- Build secret, publication check, step text, corrections, skill docs; first review's four gaps (gap 3 is unreadable-repository-items).
- Second review (7e4f244): PlanManifest.from_yaml, Repository.settings_url, initial_branch in tests; four threads resolved. Merged main with #140 (3e6140b). Warnings on the read-access step: public site (165748f), classic token can write (1bf6d09); pushed. Per-owner tokens are team-basstler/per-owner-read-tokens.

## Next
- Owner's decision on the one open thread: duplicates guard (no change made).
- CI at 1bf6d09 not yet read. PR stays draft.
