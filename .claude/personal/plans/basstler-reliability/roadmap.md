# basstler-reliability - standing rules

- What was not read is not checked: a command that cannot decide exits with a status of its own and prints no passing answer, and a skill never reports it as fine.
- A gate depends only on the checks its step needs, named with check-setup.sh --only, never on the overall exit code.
- Conflicts are decided by git (basstler.sh stack merge-probe), never by GitHub's mergeable_state.
- Every skill command is one self-contained Bash call; tests/skills enforces it for every document.
- This plan fixes today's skills; the one-command brief and skill evals belong to basstler-v3.
- ListedRuns (tests/upstream_reviews/test_action.py) records raw GET paths. Model the listing request (repository, branch, runs per page) beside RunListing.path, record it in the double, assert listing.branch instead of parse_qs. Check the other run-listing test doubles. Start after PR #191 lands (shares test_action.py).
