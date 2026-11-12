# Keeping a plan's manifest current

## The rule

- **Write the manifest at every transition**, before the work that follows: a change to
  an item's `status`, `branch`, `pull_request_number`, `session`, `notes` or `blockers`,
  or to the plan's items.
- **Every write is a push to the notes branch, which rebuilds the plan's page on the
  plan site.** Nothing is republished by hand; when you report, link the page with
  `plan_site_page_url <plan-id> [<item-id>]`.
- Read only what the step needs.

## Writing a field

```bash
"${BASSTLER_PLUGIN_ROOT}/hooks/basstler.sh" plan.item_bootstrap update --plan <plan-id> --item <item-id> \
    [--status <status>] [--branch <branch>] [--pull-request-number <number>] \
    [--session <url>] [--notes <file> | --append-notes <file>] [--blockers <file> ...]
"${BASSTLER_PLUGIN_ROOT}/hooks/basstler.sh" plan.item_bootstrap check --plan <plan-id> --item <item-id>
```

- `--append-notes` adds to the recorded note; never read a note back to rewrite it.
- Separate paragraphs in a notes file with blank lines; the report's `note_paragraphs`
  is the count written.
- `check` compares the manifest against local git and exits `manifest_is_stale` on a
  contradiction.
- A standing rule for every later item goes through `record --roadmap-entry`.
- Create the pull request yourself and pass `--pull-request-number`, so it is
  attributed to you.

## Automation holding a branch

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${BASSTLER_PLUGIN_ROOT}/hooks/basstler.sh" plan.item_bootstrap resolve --branch <branch>
"${BASSTLER_PLUGIN_ROOT}/hooks/basstler.sh" plan.item_bootstrap block --branch <branch> \
    --owner "${MAINTENANCE_BLOCKER_OWNER}" --reason <file>
"${BASSTLER_PLUGIN_ROOT}/hooks/basstler.sh" plan.item_bootstrap unblock --branch <branch> \
    --owner "${MAINTENANCE_BLOCKER_OWNER}"
```

Each prints the branch's item as `tracked_item` and touches only blockers under its own
owner. A branch no plan tracks exits `branch_tracks_no_item`; report it. Write only
what was decided mechanically. A landed branch needs no write: its item's page shows it
`done` once its pull request merges.
