Plan
- `_rules.yaml` on the notes branch (id, text), edited by `basstler repository-rules`.
- Brief prints `repository_rules`; plan pages show them; plan-create links them.

Done
- Model, store, command, brief, site section, skill text, tests; pydantic added with approval.
- Restacked onto main (874caa8); `ValidatedJSONModel` imported from `basstler.json_model` (67cf76c).
- Several rules in one push: `repository-rules import <file>`, a YAML file in the rules file's own format, validated before pushing (75c1f44). Owner asked for the cleanest, most reliable syntax; chose the file over `--rule id=text` and positional pairs.
- Test docstrings: the code-rules pre-commit hook requires them on touched test classes/functions, so touched ones now have them; untouched tests left alone.
- At 75c1f44: ruff, format, pre-commit hooks pass; tests 2336 passed, 1 skipped (without test_draft_recheck.py).

Next
- Owner: review the import command and resolve the plan-create thread.
- After merge: seed the rules with `repository-rules import`, then drop the personal-notes "Design priorities" section.
