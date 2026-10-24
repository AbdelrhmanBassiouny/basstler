# First-time setup

Five steps, once per person and project. They give you personal notes that follow you
across sessions, per-pull-request progress tracking, and multi-PR plan dashboards.

Details of everything below: [`hooks/README.md`](../plugin/hooks/README.md).

## 0. Add the plugin

basstler is a Claude Code plugin, and this repository is its marketplace.

- **Cloud sessions (claude.ai):** add it under Customize > Plugins, from the marketplace
  `AbdelrhmanBassiouny/basstler` - or have an organization Owner install it for members.
  Plugins a repository names in its own settings do not load in cloud sessions.
- **Local sessions and CI:** `/plugin marketplace add AbdelrhmanBassiouny/basstler`, then
  `/plugin install basstler@basstler` - or enable it for everyone working on a project in
  its committed `.claude/settings.json` (`extraKnownMarketplaces` and `enabledPlugins`).

The plugin's session start installs the package at the plugin's own version into
`~/.local/share/basstler/venv` (`$BASSTLER_HOME/venv` when set) - nothing to install by hand.

## 1. Run the setup

In any Claude Code session on the project:

```
/setup-personal-notes
```

It creates your notes branch, records the git identity your commits are authored
with, installs what the dashboards need, and asks only about the decisions that
are genuinely yours. Re-running it on a set-up project changes nothing.

## 2. Do the steps no script can do

```bash
~/.local/share/basstler/venv/bin/python -m basstler.setup_steps
```

The session start created that environment; see the repository's [`README.md`](../README.md).

It prints these three, already filled in for your fork:

| Where | What |
| --- | --- |
| Your fork | Create the `merged`, `bug` and `in-review` labels. |
| Your Claude settings | Give Claude access to the fork on GitHub. |
| Your Claude environment | Paste the `CLAUDE_PERSONAL_NOTES_*` variables — only if you moved a setting off its default, and only for environments that clone fresh each session. |

## 3. For the stacked-PR workflow: name the project's upstream

Only if the project uses `/stacked-pr-maintenance` or `/upstream-reviews`. Commit
`.claude/basstler/stack.toml` naming the repository the project's pull requests are
reviewed on:

```toml
upstream_repository = "<owner>/<name>"
```

and, for `/upstream-reviews`, copy [`examples/upstream-reviews.yml`](examples/upstream-reviews.yml)
to the project's `.github/workflows/upstream-reviews.yml` on its default branch. It calls this
repository's reusable workflow and installs the package, both from `main`; to pin a release
instead, change both references to its tag.

## 4. Check it worked

```bash
"${BASSTLER_PLUGIN_ROOT}/hooks/check-setup.sh"
```

Every row `ok` and you are done. Anything left says what it needs. Every session
start prints the same verdict, so you never have to remember to check.
