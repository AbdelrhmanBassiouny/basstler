---
name: upstream-reviews
description: Report the CI checks and review threads a fork branch's upstream pull request has collected, including which checks failed, the log behind each failure, and which threads are still unresolved, by dispatching basstler's upstream-reviews Action and reading its job log, so the project itself commits nothing. Invoke as "/upstream-reviews [<pull-request-number>|<branch>]". Use when the user asks what the upstream reviewers said, how a promoted branch's CI is doing upstream, why an upstream check failed, whether it has outstanding review comments, or to check upstream state before resolving or resuming work on a branch.
allowed-tools: Bash, Read, mcp__github__actions_run_trigger, mcp__github__actions_list, mcp__github__get_job_logs, mcp__claude-code-remote__add_repo
---

# Upstream reviews

Reads the check and review state of a fork branch's pull request on the
upstream repository, and on request the log behind each check that failed, and
reports it. Generic and fork-agnostic — nothing here may hardcode a repository,
owner, or branch name.

**This skill only reads.** It never comments on, reviews, resolves, or
otherwise modifies anything on the upstream: the upstream belongs to its
reviewers, and the report is the entire deliverable.

## Why an Action rather than a direct read

Thread resolved-state is exposed only by GitHub's GraphQL API, and GraphQL is
blocked for Claude sessions by the agent proxy's egress policy — for every
repository, including the fork's own. The upstream is worse off still: a Claude
session's GitHub access is scoped to the repositories attached to it, so the
upstream's REST API answers 403 as well, and its check results cannot be read
from the session at all. The read therefore happens on an Actions runner, where
`gh` is preinstalled and `GITHUB_TOKEN` authenticates it, and this session reads
the resulting job log, which is plain read-only REST.

The runner is basstler's own repository rather than the project's: its
`upstream-reviews-dispatch.yml` takes the upstream and the fork owner as inputs,
so a project needs neither a workflow nor a committed `stack.toml` for this
skill to work there.

## 0. One-time prerequisites

The upstream has to be named somewhere `stack configuration` reads it: the
project's committed `.claude/basstler/stack.toml`, or the user's own
`.claude/personal/stack.toml` on the personal-notes branch. Check for it, and
everything else this skill relies on, first: follow
`skills/setup-personal-notes/prerequisite-check.md`, passing
`--require-upstream` to `check-setup.sh` so a missing upstream runs the setup
(which asks for it) instead of failing in step 1.

Dispatching a workflow takes write access to the repository it runs in, so
the reviews repository (step 1) must be one the user can push to. A user who
cannot push to basstler's own repository sets `reviews_repository =
"<owner>/<name>"` in their personal `stack.toml`, naming a copy of basstler
whose default branch carries `upstream-reviews-dispatch.yml`. If the dispatch
fails because Actions are disabled there, say so and point the user at that
repository's Settings → Actions rather than retrying.

## 1. Resolve the target, the fork, the upstream and the reviews repository

Resolve them rather than assuming:

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${BASSTLER_PYTHON}" -m "${STACK_MODULE}" configuration
```

Read `fork_repository`, `upstream_repository` and `reviews_repository` from its
output; the fork owner is `fork_repository`'s owner.

Take the target from the skill's argument: a bare number is an upstream pull
request number, anything else is a branch name. With no argument, use the
current branch (`git rev-parse --abbrev-ref HEAD`).

The reviews repository is usually not one the session was started with. If
the dispatch is refused because the repository is not configured for the
session, attach it with `mcp__claude-code-remote__add_repo` (`access:
"push"`) and dispatch again; if that is refused too, relay its reason.

## 2. Dispatch the workflow

Call `mcp__github__actions_run_trigger` with `method: "run_workflow"`,
`workflow_id: "upstream-reviews-dispatch.yml"`, the reviews repository as
`owner`/`repo`, `ref` set to that repository's default branch, and `inputs`
carrying `upstream` (the upstream's `owner/name`), `fork_owner`, and either
`pull_request` or `branch`, plus `include_resolved` when the user asked for
resolved threads too and `failure_logs` when they asked why a check failed.

`failure_logs` costs one extra REST call per failed check and quotes up to 40
lines of each job's log, so it is off by default: ask for it when a red check
needs explaining, not on every read.

This dispatch is the only call in the skill that is not a read. It starts a
job in the reviews repository and changes no repository content.

## 3. Wait for the run

List runs with `mcp__github__actions_list`, `method: "list_workflow_runs"`,
`resource_id: "upstream-reviews-dispatch.yml"` on the reviews repository, and
`workflow_runs_filter.event: "workflow_dispatch"`. Take the newest run created
after the dispatch, and poll it until its status is `completed`. Runs of this
workflow have historically started with no queue delay and the job itself is
small, so expect well under a minute. Do not use a fixed `sleep` loop as a substitute for checking status.

## 4. Read the report

Get the run's jobs with `method: "list_workflow_jobs"`, then call
`mcp__github__get_job_logs` with that `job_id` and `return_content: true`. The
report is the markdown the script printed; the same text is also on the run's
job summary, which the user can read from the GitHub mobile app.

## 5. Present it

Reproduce the report's substance in the session: the checks verdict with every
check that did not pass, and every unresolved thread with its author,
`file:line`, and comment text. Do not summarize away the comment bodies — the
point of the skill is that the reviewer's actual words reach the session
without the user retyping them.

The checks section names only the checks that did not pass, alongside the
verdict GitHub itself computed and how many of the total passed. A check still
running reads as `pending`, which is not the same as passing.

With `failure_logs`, each failed check is followed by an excerpt of its job's
log: pytest's own summary where the job ran that far, the runner's error
annotations where it died before that, and the log's last lines where neither
marker appears. A check whose link names no Actions job — a status posted by
some other service — has no log to quote and is left with its verdict alone.

If the run failed, report the failure and the log's error rather than an empty
result. If the branch has no upstream pull request, the script says so
explicitly — relay that as a clean answer, not an error.
