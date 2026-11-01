## Plan
- Make Item.branch optional in the dashboard model and its card (tests first).

## Done
- Failing tests, fix (`.get`, `str | None`, branch label omitted when absent), commit, draft PR 107 (bug label, patch).

## Next
- Owner review. Hook/setup tests fail in the cloud environment only (git author env vars, plugin venv).
