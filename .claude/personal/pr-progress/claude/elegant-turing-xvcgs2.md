PR https://github.com/AbdelrhmanBassiouny/basstler/pull/5 (draft, bug): every merge to main is a release. release.yml bumps the patch on merge and pushes the commit and tag atomically. PRs may only name the next minor or major (`release_version check`).

Plan:
- Release on merge, minor/major via `release_version bump`, check on PRs. Branch stays at 0.1.0, so merge releases v0.1.1.

Done:
- Review rounds 1-2. Confirmed that a session start with an untagged plugin version keeps the old package (fresh env: none). Bump-on-merge in e0715bf. 845 tests pass.

Next:
- User to check branch protection lets the release job push to main. Wait for review.
