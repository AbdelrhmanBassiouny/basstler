PR https://github.com/AbdelrhmanBassiouny/basstler/pull/5 (draft, bug): fail a PR that changes what basstler ships (src, pyproject, plugin/, reusable workflow) without bumping plugin.json's version; `release_version bump` writes it everywhere.

Plan:
- `release_version check` in CI; `release_version bump`; version 0.1.1.

Done:
- Review round 1 (a8d4a4a): plugin/skills count, bump command, fields before exit_code. Threads replied and resolved. 838 tests pass.

Next:
- Wait for the user's review. On merge, release.yml tags v0.1.1.
