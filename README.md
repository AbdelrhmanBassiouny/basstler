# basstler

Workflow tooling for Claude Code sessions: personal notes that follow you across sessions,
per-pull-request progress, multi-PR plans on a live plan site, stacked-pull-request
maintenance and an upstream review reader.

The name is the German word for someone who builds things themselves, and shares its
first letters with the surname of the person who wrote it, Bassiouny.

basstler is maintained in the [KAOS-repositories](https://github.com/KAOS-repositories)
organization on GitHub. Setting it up: [`docs/SETUP.md`](docs/SETUP.md).

## What is in this repository

| Path | What it is |
| --- | --- |
| `plugin/` | The Claude Code plugin: its manifest, the skills, and the bash hooks the skills and the session start run. |
| `.claude-plugin/marketplace.json` | The marketplace that lists the plugin, so this repository is what you add it from. |
| `src/basstler/` | The Python package every hook and skill runs, as `python -m basstler.<module>`. |
| `tests/` | The test suite, run by `pytest tests`. |
| `docs/` | The setup guide and the stacked-PR workflow. |

The plugin carries no Python, and the package carries no hooks: a session start installs the
package at the plugin's own version, so the two are always one release.

## Releasing

Every push to `main` that changes anything is a release once its Tests run passes, made by
`release.yml`. A commit whose tests fail is never tagged, so installs stay on the latest
release that passed, and the next passing commit releases everything merged since. An install
takes the package from its plugin's release tag, so a change merged without one would reach
no install at all. Every change counts, not only those to the package, since a list of
shipped paths would go stale.

- **A release is only a tag on the merge commit.** No file on `main` names the version -
  the build reads it from the tag (`hatch-vcs`), and `plugin/.claude-plugin/plugin.json`
  names none - so nothing is pushed to `main` after a merge.
- **The plugin is served from the `plugin-release` branch,** which the same atomic push
  moves to the tag's `plugin/` directory alone, alongside the `release` branch it moves to
  the tag (`.claude-plugin/marketplace.json` names it as the plugin's `ref`). Its
  `plugin.json` gains the release's `version`, so claude.ai and Claude Code show which
  release a synced plugin is. A synced plugin is therefore always a release, and its
  session start installs that same release: a merge whose tests fail, or are still
  running, reaches no install at all.
- **The workflow increments the latest release's patch,** or its minor or major part when a
  pull request merged since is labelled `release:minor` or `release:major`. It then
  publishes a GitHub release with generated notes.
- **A session start installs the tag its plugin's `plugin.json` names,** and a hook
  installs again once the plugin syncs to another release. Where the two still differ, as
  after an install that failed, the session start's `release:` line and check-setup's
  `basstler_version` row say so, the row with the status `mismatched`.

## The package's own environment

**Every session start gives `basstler` an environment of its own, without asking:** one per
project, under `~/.local/share/basstler/environments` (`$BASSTLER_HOME/environments` when
`BASSTLER_HOME` is set), from an interpreter the package supports, with the package installed
into it at that project's plugin release. Worktrees of a project share its environment, and a
session runs its project's environment in every repository it has attached; the session start
exports it as `$BASSTLER_ENVIRONMENT_DIRECTORY` and its interpreter as `$BASSTLER_PYTHON`. Its
`environments:` line names any environment it removed because its project directory is gone.

What it installs from depends on where the plugin is:

- **A plugin installed on its own** installs `basstler @ git+https://github.com/KAOS-repositories/basstler@<tag>`,
  the tag being the release its `plugin.json` names. A plugin naming none - a copy of the
  source tree outside a clone - installs nothing: session start says so on its
  `dependencies:` line, every hook stops with the same reason, and setup reports it as
  `mismatched`. Reinstall the plugin from the marketplace.
- **A plugin run from a clone of this repository** installs that clone editable, so
  `import basstler` is the clone's own source.

The environment comes from `uv` where it is on the path, since `uv` can fetch a supported
interpreter where none is installed, and otherwise from the newest supported `python3.1x`
on the path. A machine with neither - one whose only interpreter is too old - gets `uv`
installed into `$BASSTLER_HOME/uv` with the `pip` it has, and `uv` fetches the interpreter.
`uv` also does the installing wherever there is one, since `pip` runs inside the
environment's own interpreter and an older `pip` breaks on a newer one.

Three things bound it:

- **Only for someone who has already set the tooling up.** The hook stops before this
  point when it cannot reach your personal-notes branch, so a project that has never run
  `/setup-personal-notes` installs nothing at all.
- **Only what is missing or out of date.** The usual start finds the environment installed
  from the source the plugin names, looks the requirements up and runs no installer. A
  plugin update names a new source, and the environment is installed into again - also
  when the plugin is synced during a session, which a hook notices from the plugin's
  content changing since the install.
- **Never fatal.** No `pip` to install `uv` with, or no network: the summary's
  `dependencies:` line says so, naming the command to run, and the rest of the run carries
  on.

An Actions runner reaches no session hook, so a workflow that runs a module installs the
package itself - `tests/test_package_contract.py` finds every such workflow and checks that
it does.

## Running it

Every entry point is run as a module, by the package's own interpreter:

```bash
"$BASSTLER_PYTHON" -m basstler.stack configuration
"$BASSTLER_PYTHON" -m basstler.maintenance run-report --json
"$BASSTLER_PYTHON" -m basstler.plan_site --help
```

The hooks and the skills that call them all use `"${BASSTLER_PYTHON}" -m "${SOME_MODULE}"`,
with the interpreter and each module named once in
`plugin/hooks/resolve-personal-notes-config.sh`. A session finds that file through
`BASSTLER_PLUGIN_ROOT`, which the plugin's session start exports.

## Developing it

```bash
uv venv --python ">=3.12" .venv && uv pip install --python .venv/bin/python --editable . --group dev
.venv/bin/python -m playwright install chromium
PATH="$PWD/.venv/bin:$PATH" pytest tests -n auto
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The hook tests run `python3`, so the environment has to be first on the path, and the plan
page's script is tested in the headless Chromium Playwright installs. `ruff check`
enforces the mechanical code rules, configured in `pyproject.toml`. Python is formatted
by `python scripts/format_docstrings.py <files>` (ruff format, then docformatter where ruff
keeps its result), also run as a pre-commit hook. The rule-check and AGENTS.md hooks
run `.venv/bin/python`, so they need the environment set up above. To try a
change in a real session, start Claude Code with `--plugin-dir plugin`: the plugin then
sits in this clone, and installs the clone editable.

## Licence

basstler was written by Abdelrhman Bassiouny (<bido.bassuny@gmail.com>), independently of any
employer or institution, and is maintained in the
[KAOS-repositories](https://github.com/KAOS-repositories) organization, which Abdelrhman
Bassiouny co-founded. It is licensed under
the [Apache License 2.0](LICENSE). The few modules adapted from
[krrood](https://github.com/cram2/cognitive_robot_abstract_machine/tree/main/krrood) keep
krrood's licence, the LGPL-3.0; [NOTICE](NOTICE) names them.

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
