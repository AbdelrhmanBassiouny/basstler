PR #77 - plan stack-maintenance / item stack-state-from-github (auto mode). Draft, release:minor.

Plan:
- in-review from the open upstream PR (board export, no label fallback); pass mirrors label + description link.
- check_state: RollupState on the board from fork head checks; promotion withholds failure/error.

Done:
- Implemented, main merged (af8360f). Review round 1 (74b9e50): UpstreamPullRequests rename, UpstreamReviewMirror class (label + "## Upstream pull request" link), description sections replaced in place, dashboard card "upstream" link from body, PackageLocation.BOARD in tests. Full suite = main's 14 env failures only.

Next:
- Owner: docstring thread on GitHubRepository.check_state left open (AGENTS.md says overrides inherit; asked whether to add anyway).
- Owner review. A cloud pass needs the upstream attached (add_repo) or the export stops (403) - by design per #15 thread.
- After merge: resolve the three #15 threads (r4368830083, r4368930418, r4368930516).
