# Gathering a tracked plan item's context

Shared by `plan-item-kickoff` and `plan-item-resolve`: what is already known and
decided about the item, before either acts.

## 1. Setup

Run [`prerequisite-check.md`](../setup-personal-notes/prerequisite-check.md)'s check
first.

## 2. The stack, only when an upstream is named

When `bash "${CHECK_SETUP_SCRIPT}" --require-upstream` exits 0, run
`/stacked-pr-maintenance` first, then fix any conflict on the item's branch or a branch
it is stacked on (on that branch's own pull request) and run the pass again. Otherwise
skip this.

## 3. The brief

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${BASSTLER_PYTHON}" -m "${ITEM_BRIEF_MODULE}" --plan <plan-id> (--item <item-id> | --branch <branch>)
```

It prints the plan's id, title and `tracking_issue`, the item's entry, each
`depends_on` entry's live state with `is_ready`, and the plan's standing rules. Read
nothing else of the plan: other items are other sessions' work.

- Given a pull request number, read its head branch with
  `${GITHUB_PULL_REQUEST_READ_TOOL}` (`method: "get"`), find its plan with
  `plan_id_for_branch <branch>` after `fetch_personal_notes_branch`, and pass
  `--branch`. No plan means the pull request is *untracked*: say so and skip the brief.
- An unknown plan or item fails; list what exists rather than guessing.
- Each standing rule binds the item as much as its own `notes`. `blockers` is often the
  plainest statement of what is wrong; `session` links earlier work, as context only.
- A dependency with `is_ready: false` decides what a branch can be based on: flag it
  in whatever you propose, never proceed as if it were ready.

## 4. The tracking issue

If there is a `tracking_issue`, read its comments with `mcp__github__issue_read`
(`method: "get_comments"`) now and before each push: structural changes to the plan
are posted there. A failed read is mentioned, not fatal.

## 5. The project's rules

Read `AGENTS.md` (else `CLAUDE.md`). Whatever you propose honors both it and the
standing rules.

## Before raising an open question

Re-read the standing rules, the item's `notes` and `blockers`, and any pull request or
thread they cite: most questions are already answered there. Ask only what is still
open, and say what you checked.
