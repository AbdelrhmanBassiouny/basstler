PR #102 - save-plan-scoped-limits

Plan
- Plan measured against the stored manifest; unchanged items' violations become warnings.
- Plan-level limits stay refusals.

Done
- Failing tests, implementation, black; pushed.
- Full suite: 58 failures, all from subprocess tests lacking yaml/jinja2/rustworkx (environment).

Next
- Run docformatter via the pre-commit hook; owner review.
