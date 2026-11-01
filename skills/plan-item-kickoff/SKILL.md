---
name: plan-item-kickoff
description: Start one tracked plan item: gather its context, open its branch and draft PR, record it, then plan or implement per the execution mode. Invoke as "/plan-item-kickoff <plan-id> <item-id>". Use from a plan page's "Start now" link or when asked to start or kick off an item.
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, AskUserQuestion, Skill, EnterPlanMode, ExitPlanMode, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__get_file_contents, mcp__github__create_pull_request, mcp__github__update_pull_request, mcp__claude-code-remote__subscribe_pr_activity, mcp__github__issue_read
---

# Plan Item Kickoff

Plan-agnostic: never hardcode a plan id, item or branch. Step 1 creates nothing.

## 1. Gather

Follow [`plan-item-gathering.md`](../plan-item-kickoff/plan-item-gathering.md). Then learn
the pattern this item follows from what landed: for the files it will touch, find the
merged pull requests that last changed them (`git log <base> -- <paths>`) and read their
diffs and descriptions (`mcp__github__pull_request_read`), including review-driven
decisions. If the item's branch already exists, build on what is on it.

## 2. Resolve the mode

Follow [`execution-modes.md`](../plan-item-mode/execution-modes.md) with
`--skill kickoff`, passing `--requested <mode>` only when the invocation named one.

## 3. Draft the plan

Check the unit of work with [`scope-decision.md`](../add-plan-item/scope-decision.md):
propose folding if nothing substantial remains once overlapping edits are removed;
otherwise name the overlapping files. Then plan what changes, in which files and order,
and how each part is verified (tests first). Cite each part's source (the item's notes,
a merged pull request, a standing rule) and flag any dependency not ready, any conflict
between the notes and what landed, and anything still open.

Read `plan-create/plan-schema.md` only when the plan changes the plan's structure.

In `plan` mode present it with `ExitPlanMode` and stop. In `auto` mode it is settled;
the flags go into the pull request description. No git or code in this step.

## 4. Bootstrap, before the first edit

```bash
git checkout -b <branch> <base-branch>
git commit --allow-empty -m "Bootstrap <item-id>"
git push -u origin <branch>
# create the draft pull request yourself, so it is yours, then:
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}" open --plan <plan-id> \
    --item <item-id> --branch <branch> --base <base-branch> \
    --session <this session's url> --pull-request-number <number>
"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}" record --plan <plan-id> \
    --item <item-id> --status "in progress" [--roadmap-entry "<a new standing rule>"]
```

The base follows dependency readiness; the branch is the one this session develops on.
Both commands print a JSON report led by `status` and `exit_code`.

Write the plan down:

- **The pull request description**: what was decided and why, with its assumptions.
- **`--roadmap-entry`**: only a rule binding every later item, as one sentence.
- **The PR-progress note**: Plan, Done, Next as short lists, replaced rather than
  accumulated, saved with
  `"${BASSTLER_PLUGIN_ROOT}/hooks/save-pr-progress.sh" --branch <branch> --source <file>`
  as soon as the branch exists.

Then give the item's page on the plan site, `plan_site_page_url <plan-id> <item-id>`,
which the record's push rebuilds. Later transitions follow
[`manifest-staleness.md`](../plan-sync/manifest-staleness.md).

In `plan` mode the skill ends here.

## 5. Implement, in `auto` mode

Work the plan with tests first, committing in the user's own identity. Keep the pull
request a draft and its description and progress note true to the work; record
decisions as they are made, and stop to ask only past the bar in
[`execution-modes.md`](../plan-item-mode/execution-modes.md). Work that needs more than
this pull request goes to the plan's tracking issue and the user. Finish by reporting
what was built and decided.
