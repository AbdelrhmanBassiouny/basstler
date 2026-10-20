---
name: upstream-reviews
description: Report the CI checks and review threads a fork branch's upstream pull request has collected, including which checks failed, the log behind each failure, and which threads are still unresolved, by attaching the upstream to the session and reading it over REST, so the project itself commits nothing. Invoke as "/upstream-reviews [<pull-request-number>|<branch>]". Use when the user asks what the upstream reviewers said, how a promoted branch's CI is doing upstream, why an upstream check failed, whether it has outstanding review comments, or to check upstream state before resolving or resuming work on a branch.
allowed-tools: Bash, Read, Skill, mcp__claude-code-remote__add_repo
---

# Upstream reviews

Reads the check and review state of a fork branch's pull request on the
upstream repository, and on request the log behind each check that failed, and
reports it. Generic and fork-agnostic — nothing here may hardcode a repository,
owner, or branch name.

**This skill only reads.** It never comments on, reviews, resolves, or
otherwise modifies anything on the upstream: the upstream belongs to its
reviewers, and the report is the entire deliverable.

## How the read reaches the upstream

A Claude Code cloud session's proxy refuses GitHub's GraphQL API, but answers
REST for every repository attached to the session — including a
review-threads route of its own that carries each thread's resolved state,
which GitHub otherwise keeps behind GraphQL. So once the upstream is attached,
`basstler.upstream_reviews` reads everything itself and parses it into the same
models a runner's GraphQL read builds. Nothing runs in Actions, and nothing is
committed to the project.

Anywhere else — Claude Code in a terminal on the user's own machine, or a
runner — there is no proxy: the module reads GraphQL with whatever `gh` is
logged in as. Reading needs only read access to the upstream (any account can
read a public one), never push access.

## 0. One-time prerequisites

The upstream has to be named somewhere `stack configuration` reads it: the
project's committed `.claude/basstler/stack.toml`, or the user's own
`.claude/personal/stack.toml` on the personal-notes branch. Check for it, and
everything else this skill relies on, first: follow
`skills/setup-personal-notes/prerequisite-check.md`, passing
`--require-upstream` to `check-setup.sh` so a missing upstream runs the setup
(which asks for it) instead of failing in step 1.

## 1. Resolve the target, the fork and the upstream

Resolve them rather than assuming:

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${BASSTLER_PYTHON}" -m "${STACK_MODULE}" configuration
```

Read `fork_repository` and `upstream_repository` from its output; the fork
owner is `fork_repository`'s owner.

Take the target from the skill's argument: a bare number is an upstream pull
request number, anything else is a branch name. With no argument, use the
current branch (`git rev-parse --abbrev-ref HEAD`).

## 2. Attach the upstream to the session (cloud sessions only)

Outside a Claude Code cloud session (`CLAUDE_CODE_REMOTE` is not `true`) skip
this step: there is nothing to attach. If step 3 then fails to authenticate,
tell the user to run `gh auth login` (or set `GH_TOKEN`) with an account that
can read the upstream, and stop.

In a cloud session, call `mcp__claude-code-remote__add_repo` with the upstream's owner and name and
`access: "push"`. The access level is what makes the proxy answer the
upstream's REST API at all — `"read"` covers git clones only. Nothing is ever
pushed: a result saying pushes would be refused is expected and fine. Skip the
clone the result suggests; the read needs none.

If the attach itself is refused, relay its reason and stop.

## 3. Read it

```bash
"${BASSTLER_PYTHON}" -m "${UPSTREAM_REVIEWS_MODULE}" \
  --upstream <upstream owner/name> --fork-owner <fork owner> \
  (--pull-request <number> | --branch <branch>) \
  [--include-resolved] [--failure-logs]
```

Add `--include-resolved` when the user asked for resolved threads too, and
`--failure-logs` when they asked why a check failed. `--failure-logs` costs one
extra request per failed check and quotes up to 40 lines of each job's log, so
ask for it when a red check needs explaining, not on every read.

It picks the REST reader by itself inside a cloud session; `--source rest`
forces it if it ever guesses wrong.

## 4. Present it

Reproduce the report's substance in the session: the checks verdict with every
check that did not pass, and every unresolved thread with its author,
`file:line`, and comment text. Do not summarize away the comment bodies — the
point of the skill is that the reviewer's actual words reach the session
without the user retyping them.

The checks section names only the checks that did not pass, alongside the
verdict and how many of the total passed. A check still running reads as
`pending`, which is not the same as passing.

With `--failure-logs`, each failed check is followed by an excerpt of its job's
log: pytest's own summary where the job ran that far, the runner's error
annotations where it died before that, and the log's last lines where neither
marker appears. A check whose link names no Actions job — a status posted by
some other service — has no log to quote and is left with its verdict alone.

If the command exits non-zero, report its error rather than an empty result.
If the branch has no upstream pull request, it says so explicitly — relay that
as a clean answer, not an error.
