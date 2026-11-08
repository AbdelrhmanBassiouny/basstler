Plan
- `_rules.yaml` on the notes branch (id, text), edited by `basstler repository-rules`.
- Brief prints `repository_rules`; plan pages show them; plan-create links them.

Done
- Model, store, command, brief, site section, skill text, tests; pydantic added with approval.
- #158 landed; branch restacked onto main (5c02070), base is main.
- Followed #158's move of `ValidatedJSONModel` to `basstler.json_model` (67cf76c): the old import broke every module importing the rules.
- At 67cf76c: ruff check and format pass, code-rules check passes, tests 2330 passed, 1 skipped (without test_draft_recheck.py); merge probe of 5c02070 against main was clean.

Next
- Owner: choose the syntax for setting several rules in one call (thread on plan-create/SKILL.md), then implement it.
- Owner: close or redirect the pydantic design thread on repository_rules.py.
- Owner: the test-docstring question in the PR description.
- After merge: seed the rules with `repository-rules set`, then drop the personal-notes "Design priorities" section.
