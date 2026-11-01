# Keeping a plan's manifest current

## The rule

- **Write the manifest at every transition**, before the work that follows: a change to
  an item's `status`, `branch`, `pull_request_number`, `session`, `notes` or `blockers`,
  or to the plan's items.
- **Republish the dashboard once per turn**, after the turn's last manifest write and
  before you report. Several writes in one turn get one republish. A turn with no write
  gets none.
- Read only what the step needs. Never read a published dashboard back.

## Writing a field

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}" update --plan <plan-id> --item <item-id> \
    [--status <status>] [--branch <branch>] [--pull-request-number <number>] \
    [--session <url>] [--notes <file> | --append-notes <file>] [--blockers <file> ...]
"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}" check --plan <plan-id> --item <item-id>
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
"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}" resolve --branch <branch>
"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}" block --branch <branch> \
    --owner "${MAINTENANCE_BLOCKER_OWNER}" --reason <file>
"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}" unblock --branch <branch> \
    --owner "${MAINTENANCE_BLOCKER_OWNER}"
```

These write every item on the branch, and they touch only blockers written under their
own owner. A branch no plan tracks exits `branch_tracks_no_item`; report it. Write only
what was decided mechanically. A landed branch is set to `done` by the dashboard
refresh.
