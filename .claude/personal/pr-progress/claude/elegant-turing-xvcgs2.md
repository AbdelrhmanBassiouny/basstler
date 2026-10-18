PR https://github.com/AbdelrhmanBassiouny/basstler/pull/5 (draft, bug): fail a PR that changes the package without bumping plugin.json's version.

Plan:
- basstler.release_version check + CI release-version job; bump to 0.1.1.

Done:
- Module, 7 tests, CI job, README, bump to 0.1.1; 820 tests pass; pushed and PR opened.

Next:
- Wait for the user's review; on merge, release.yml tags v0.1.1.
