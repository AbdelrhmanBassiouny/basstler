## Plan
Port the session-free personal-notes setup onto main's src layout as
`python -m basstler.setup.personal_notes`; SKILL.md keeps only the questions.
Labels: main's `GitHubLabel` set as is (owner's call, 2026-10-25).

## Done
- Ported command, report model, label API; live label creation verified.
- Review round 1 (paths, keys, email, exit codes) addressed in 86091fe.
- Malformed --email refused in the error's own words (4ccf9cf); 1300 tests green.

## Next
- Leave draft until told otherwise.
