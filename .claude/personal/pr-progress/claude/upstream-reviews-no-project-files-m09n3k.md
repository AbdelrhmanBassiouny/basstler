## PR #56 - /upstream-reviews without committed project files

Plan
- Reusable workflow takes optional `upstream`/`fork_owner` inputs.
- basstler gets a dispatch-only `upstream-reviews-dispatch.yml` calling it at `github.sha`.
- `stack configuration` prints `reviews_repository` (default: basstler; override in stack.toml).
- Skill dispatches there with upstream + fork owner from `stack configuration`; SETUP.md section 3 made optional.

Done
- Branch, draft PR #56, manifest `in progress`.

Next
- Tests first (stack configuration, workflow inputs), then the code, skill and docs.
