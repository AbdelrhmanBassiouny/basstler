# plan-size-limits — standing rules

Moved from the CRAM fork's notes on 2026-10-18. An item carrying `repository: AbdelrhmanBassiouny/cognitive_robot_abstract_machine` still points at its CRAM-fork pull request; basstler-package's basstler-open-pull-request-carryover reopens it here and clears that line.

- The limits live in basstler/src/basstler/plan_size_limits.py (Measure) and are enforced by save-plan.sh and save-pr-progress.sh; raising one is the user's call.
- branch-index.tsv and dashboard-urls.yaml are keyed by plan id; any split or removal of a plan regenerates both, or session-start.sh stops resolving branches and /plan-dashboard mints duplicate pages.
- This plan's pull requests stack on #501 (basstler src layout): new modules go under basstler/src/basstler/ and hooks run them with "${BASSTLER_PYTHON}".
