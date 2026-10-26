PR #77 - plan stack-maintenance / item stack-state-from-github (auto mode). Draft, release:minor.

Plan:
- in-review from the open upstream PR (board export, no label fallback); pass keeps label + description link in step.
- check_state: RollupState on the board from fork head checks; promotion withholds failure/error.

Done:
- Implemented, main merged (af8360f). Review round 1 (74b9e50): UpstreamPullRequests, sync class, description link, dashboard link, PackageLocation.BOARD.
- Review round 2 (315d62a): UpstreamPullRequestSynchronization / ...Change / ...Action (module upstream_pull_request_synchronization.py, report field + --json key + summary heading follow); from_mapping and its new tests key pr_data.json by PullRequestField. Full suite = main's 14 env failures only.

Next:
- Owner: docstring thread on GitHubRepository.check_state still open (AGENTS.md says overrides inherit; asked whether to add anyway).
- Owner review. A cloud pass needs the upstream attached (add_repo) or the export stops (403) - by design per #15 thread.
- After merge: resolve the three #15 threads (r4368830083, r4368930418, r4368930516).
