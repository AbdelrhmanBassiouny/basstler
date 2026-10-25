## Plan
Port the session-free personal-notes setup onto main's src layout as
`python -m basstler.setup.personal_notes`; SKILL.md keeps only the questions.
Labels: main's `GitHubLabel` set as is (owner's call, 2026-10-25).

## Done
- Merged main, taking main's tree (the flat-layout port is dropped).

## Next
- Move check-setup.sh's report model from the test into `basstler.setup`.
- Add labels/login reads and label creation to `GitHubRepository`.
- Port the command with tests; rewrite SKILL.md; update PR #45's description.
- Label creation against a real token is still unverified (stubbed only).
