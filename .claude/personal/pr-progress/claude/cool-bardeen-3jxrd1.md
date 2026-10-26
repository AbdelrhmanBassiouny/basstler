PR #77 - plan stack-maintenance / item stack-state-from-github (auto mode).

Plan:
- Model: `ci` -> `check_state: RollupState | None`, add `upstream_pull_request: int | None`; in-review derived from it.
- Board export: list upstream open PRs once (error, no label fallback); read each fork head's checks via RestCheckRunPage/RestCombinedStatusPage/CheckStatus.over.
- Pass syncs the in-review label (add/remove, from current labels); promotion withholds failure/error; `stack status` shows checks.
- Update skill/docs that say "never adds in-review".

Done:
- Bootstrap: branch, draft PR #77 (release:minor), manifest in progress.

Next:
- Tests first for the model derivation, then board export, label sync, promotion gate, status column.
