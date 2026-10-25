## Plan
Port the session-free personal-notes setup onto main's src layout as
`python -m basstler.setup.personal_notes`; SKILL.md keeps only the questions.
Labels: main's `GitHubLabel` set as is (owner's call, 2026-10-25).

## Done
- Merged main (main's tree), ported the command, report model and label API.
- 16 tests; full suite green (1278). PR #45 description and release:minor set.

## Next
- Label creation against a real token is still unverified (in-memory only).
- Leave draft until told otherwise.
