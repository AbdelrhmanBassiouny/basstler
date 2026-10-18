# basstler-package — standing rules

- New tooling work starts here, on `main`, as a draft pull request. Carried branches get main merged in (never rebased) before their pull request opens.
- Typed invocations land before the conversion items: every conversion rewrites the same subprocess and API calls, so they are written once, in the typed form.
- The conversion items follow the carried bash-touching branches, not lead them: a wholesale body rewrite conflicts with every carried branch.
- Setup is scripted: a skill only asks the questions, and every mechanical step is a `basstler.setup_steps` subcommand with a `check-setup.sh` row. No user copies files by hand.
- Development tooling shared with other repositories comes from a pinned, published package, never a copied script.

## Where the agreed designs live

- Setup automation folded into `setup-stacked-prs-skill`: https://github.com/AbdelrhmanBassiouny/basstler/pull/1#discussion_r4306548238
- `basstler-typed-invocations`: https://github.com/AbdelrhmanBassiouny/basstler/pull/1#discussion_r4306549494 (copyable prompt at https://github.com/AbdelrhmanBassiouny/basstler/pull/1#discussion_r4306792682)
- Personal-notes redesign folded into `basstler-save-commands-python`: https://github.com/AbdelrhmanBassiouny/basstler/pull/1#discussion_r4304842666
- `cram-development-tools`: https://github.com/AbdelrhmanBassiouny/basstler/pull/1#discussion_r4306714398

## basstler-open-pull-request-carryover

- A carried branch keeps its stack: it is based here on the carried branch its CRAM-fork pull request was based on, or on main where that parent has landed (the src layout, CRAM #501, is main). Merge main into a parent before merging the parent into its children.
- Stale means written before the package existed: the misspelled `bastler/` era and the `.claude/stack/` era. A branch folded into another item, or one whose pull request closed unmerged, is retired the same way. Each retired branch gets a one-paragraph issue, and its plan item points at that issue.
- A carried item's `repository:` line is cleared once its basstler pull request exists, and `pull_request_number` names the basstler one.
