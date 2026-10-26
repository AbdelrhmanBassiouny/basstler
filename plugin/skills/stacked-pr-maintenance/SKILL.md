---
name: stacked-pr-maintenance
description: Run one maintenance pass over a fork's stacked pull requests: reparent, restack, and promote approved branches upstream. Invoke as "/stacked-pr-maintenance [fork=<owner/repo>] [upstream=<owner/repo>]". Use when asked to restack or promote the stack, and as the first step of plan-item-kickoff and plan-item-resolve.
allowed-tools: Bash, Read, Grep, AskUserQuestion, mcp__github__pull_request_read, mcp__github__list_pull_requests, mcp__github__update_pull_request, mcp__github__issue_write, mcp__github__add_issue_comment
---

# Stacked-PR maintenance

Reparent pull requests whose base has landed, run the pass, report. Why each rule below holds is in
`docs/stack/maintenance-pass.md`; you do not need it to run a pass.

## Rules

- Change no files and write no code, not even to resolve a conflict: report it and move on.
- Do not review, answer, resolve or act on review comments. If a review or comment event reaches you,
  end the turn. The one exception is a check status you are polling.
- Never call `subscribe_pr_activity`; poll checks instead. Never enter plan mode or post a plan.
- Do not fan the pass out with Claude Code's Workflow tool (subagents). The executor already does
  the fast-forward and the merges with plain git; you need only it and the GitHub MCP server.
- Never force-push a branch with an open upstream pull request unless it carries the `rebase` label.
- A label write replaces the whole set: pass exactly what `basstler.stack labels` prints.
- Never open the upstream pull request and never write `in-review` yourself.

## Step 0 - resolve the repositories

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${BASSTLER_PYTHON}" -m basstler.stack configuration [--fork <owner/repo>] [--upstream <owner/repo>]
```

Pass `fork=` / `upstream=` arguments straight through. Never inspect or guess at remotes yourself.

| exit | what you do |
|---|---|
| 0 | use it; if it printed `upstream_setup_command`, run that and re-run |
| 4 | ask which repository is the fork (options from `git remote -v`), write `fork_repository = "<owner/repo>"` to a file and save it with `"${BASSTLER_PLUGIN_ROOT}/hooks/write-personal-notes-file.sh" --source <file> --destination .claude/personal/stack.toml --message "record which repository is my fork"`, re-run |
| 11 | ask for the upstream, save it with `"${BASSTLER_PYTHON}" -m basstler.setup.steps configure-upstream --repository <owner/repo>`, re-run |
| other | stop and report |

## Step 1 - reparent

```bash
"${BASSTLER_PYTHON}" -m basstler.maintenance board --write
"${BASSTLER_PYTHON}" -m basstler.stack reparents
```

For each `branch<TAB>pr<TAB>current base<TAB>target base` line, set the pull request's base with the
MCP `update_pull_request` tool.

If that fails with `422 ... part of a stack`, the pull request is in a native GitHub stack. Call the
stacks endpoints with curl, `GH_TOKEN` and the header `X-GitHub-Api-Version: 2026-03-10`:

1. `GET /repos/{owner}/{repo}/stacks`; record the stack's pull requests, bottom to top. Do not go on
   without it.
2. `POST /repos/{owner}/{repo}/stacks/{number}/unstack`.
3. `update_pull_request` each orphaned child's base. Never close and reopen it instead.
4. Restack (step 2).
5. `POST /repos/{owner}/{repo}/stacks` with `{"pull_requests": [...]}` - the recorded list minus
   landed and closed members - then `GET` it and confirm every member reports the stack.

If any call fails or answers something not described here, stop on that stack and report it. Never
fast-forward the landed base to get around a 422.

## Step 2 - run the pass

First, for every branch `"${BASSTLER_PYTHON}" -m basstler.stack next --porcelain` names, read
its diff against its parent and write what its upstream pull request opens with, as a JSON
document in your scratchpad keyed by fork pull request number:

```json
{"<number>": {"title": "<title in the upstream's own convention>", "points": ["<point>", "..."]}}
```

Points are short sentences for an upstream reviewer who has not seen the fork pull request. Both
fields are optional; a branch you write nothing for opens with its fork title and a link back.

```bash
"${BASSTLER_PYTHON}" -m basstler.maintenance run-report --summaries <the document>
```

Do not re-derive its output, look up titles, or run the individual commands as well.

| status | what you do |
|---|---|
| `success` | relay the summary |
| `not-fast-forward` | report that the fork's base is behind the upstream |
| `move-refused` | stop; the reasons are in the summary |
| `branch-needs-attention` | relay every branch it names |

- `reparents` left in the report are made by step 1 of the next pass.
- A `restacked` entry other than `pushed` or `up-to-date` is already labelled and commented; name it.
- A `skipped` entry is not yours to fix; list it with its `reason`.
- `integration-failed` is the pass's own environment, not the branch owner's: report it as yours and
  never label the branch for it.
- A landed pull request still open after the pass is reported, never closed by you.

## Step 3 - check CI on what was pushed

Poll `pull_request_read` → `get_check_runs` / `get_status` for each branch the pass pushed; read only
the conclusion and do not wait on a long run. For a failing check, never debug it or disable it:

- comment on the fork pull request, prefixed `🔴 MAINTENANCE - NEEDS RESOLUTION:`, naming the check
  and its conclusion, written to stand alone;
- label it `needs-resolution` through `basstler.stack labels`.

## Finish

Relay `run-report`'s summary as printed, then add only what this session did:

- every reparent step 1 could not complete: number, stuck base, target base, and the native-stack
  step that stopped you;
- every failing check reported, with the comment's link;
- anything you stopped on.

## Resuming a partial run

```bash
"${BASSTLER_PYTHON}" -m basstler.maintenance board --write
"${BASSTLER_PYTHON}" -m basstler.maintenance fast-forward
"${BASSTLER_PYTHON}" -m basstler.maintenance restack
"${BASSTLER_PYTHON}" -m basstler.maintenance promote
```

`run-report` deletes the board, so a resumed run exports a fresh one first. Before any push you make
by hand:

```bash
"${BASSTLER_PYTHON}" -m basstler.stack check-move \
  --action push --source <branch> --destination <branch> --destination-remote <fork-remote>
```

Exit 5 means do not push; the reasons are on stderr.
