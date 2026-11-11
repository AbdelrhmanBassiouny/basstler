Plan:
- Page addresses name the notes repository the hub lists (#190)

Done:
- Failing session-start test (28196a3), then fix (cda11e2): `repository_name [<remote>]` reads the configured URL; `plan_site_page_url` passes the notes remote
- save-plan page test corrected with the user's agreement (it encoded the bug)
- 2509 passed locally; ruff and pre-commit pass; draft PR #198 updated

Next:
- CI on #198 (Playwright suites couldn't run locally); review
