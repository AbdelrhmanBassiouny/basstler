PR https://github.com/AbdelrhmanBassiouny/basstler/pull/5 (draft, bug): fail a PR that changes anything since the version's release tag without bumping plugin.json's version; `release_version bump` writes the version everywhere.

Plan:
- `release_version check` in CI; `release_version bump`; version 0.1.1.

Done:
- Review rounds 1-2 (a8d4a4a, 4eb03ee): bump command, any change counts (no path list), helper moved into VersionReference. All threads replied and resolved. 832 tests pass.

Next:
- Wait for the user's review. On merge, release.yml tags v0.1.1.
