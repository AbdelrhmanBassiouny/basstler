# Notes written against this release

- Read one item with `"${BASSTLER_PYTHON}" -m basstler.plan.manifest_tools item <file> --id <item-id>`.
- The limits live in `src/basstler/plan/size_limits.py`.
- Restack with `"${BASSTLER_PLUGIN_ROOT}/hooks/basstler.sh" maintenance restack`.
- A label write goes through `basstler.stack.model.PullRequest.read_board`'s board.
- The site build is `basstler.plan_site.build_start`, run on the `basstler/upstream-reviews` branch.
- Review with `/integration-conflict-triage` and plan with `/plan-create <plan-id>`.
- The board lives at `basstler/board.json`; the plugin's entry point is `hooks/basstler.sh`.
