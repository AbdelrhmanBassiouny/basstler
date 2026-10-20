---
name: upstream-reviews
description: Report the CI checks and review threads a fork branch's upstream pull request has collected, including which checks failed, the log behind each failure, and which threads are still unresolved - read by the fork's own Action on a branch of its own, or, where that cannot run, by attaching the upstream to the session or through a short-lived helper session - so the project's own branches carry nothing of basstler's. Invoke as "/upstream-reviews [<pull-request-number>|<branch>]". Use when the user asks what the upstream reviewers said, how a promoted branch's CI is doing upstream, why an upstream check failed, whether it has outstanding review comments, or to check upstream state before resolving or resuming work on a branch.
allowed-tools: Bash, Read, Skill, mcp__claude-code-remote__add_repo, mcp__claude-code-remote__create_session, mcp__claude-code-remote__get_session, mcp__claude-code-remote__list_events, mcp__claude-code-remote__archive_session
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

Preferably through the fork's own Actions. The fork carries one branch of
basstler's, `basstler/upstream-reviews`, sharing no history with the project and
holding only a workflow that calls basstler's reusable one. Pushing a request to
it starts a run, which reads the upstream over GraphQL and commits everything it
read back to the branch; `basstler.upstream_reviews_action` fetches that and
replays it through the same reader a direct read uses. It works the same from a
cloud session, a terminal or a runner, and the fork's default branch never
changes. Setup installs it (`setup_steps install-upstream-reviews-action`); the
one step no script can do is switching Actions on in a fork, which GitHub starts
with them off.

Where the Action cannot answer, the session reads the upstream itself. A Claude
Code cloud session's proxy refuses GitHub's GraphQL API, but answers REST for
every repository attached to the session — including a review-threads route of
its own that carries each thread's resolved state, which GitHub otherwise keeps
behind GraphQL. So once the upstream is attached, `basstler.upstream_reviews`
reads everything itself and parses it into the same models a GraphQL read
builds.

A session working in the fork cannot attach the upstream, though: both share a
name, and a session checks each repository out at a directory of that name. A
helper session with only the upstream attached then reads it, running the
fetch program this session hands it, and this session replays what it
recorded through the same reader (step 3a).

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

## 2. Read through the fork's Action

```bash
"${BASSTLER_PYTHON}" -m "${UPSTREAM_REVIEWS_ACTION_MODULE}" --remote "${NOTES_REMOTE}" read \
  --upstream <upstream owner/name> --fork-owner <fork owner> \
  (--pull-request <number> | --branch <branch>) \
  [--include-resolved] [--failure-logs]
```

Run it with a Bash timeout of 600000 ms: it pushes the request, waits for the
run - usually under a minute - and prints the report. The flags mean what they
mean in step 4. Then, by exit status:

- **0** — present the report (step 5).
- **1** — the read itself failed, for instance the branch was never promoted
  upstream. That is the answer: relay it as step 5 says, and stop.
- **3** — the Action could not answer. Its message says why:
  - *no `basstler/upstream-reviews` branch* — install it, then run the read once
    more:

    ```bash
    "${BASSTLER_PYTHON}" -m "${SETUP_STEPS_MODULE}" install-upstream-reviews-action --ref "v$(plugin_version)"
    ```

  - *no run started* — Actions are off on the fork. Carry on with step 3 for
    this read, and end the report by giving the user the link the message
    names: enabling Actions there once makes every later read take this path.
  - anything else (the run failed, or no result in time) — carry on with step 3,
    and say in one line that the Action failed, with the link the message names.

## 3. Attach the upstream to the session (cloud sessions only)

Outside a Claude Code cloud session (`CLAUDE_CODE_REMOTE` is not `true`) skip
this step: there is nothing to attach. If step 4 then fails to authenticate,
tell the user to run `gh auth login` (or set `GH_TOKEN`) with an account that
can read the upstream, and stop.

In a cloud session, call `mcp__claude-code-remote__add_repo` with the upstream's owner and name and
`access: "push"`. The access level is what makes the proxy answer the
upstream's REST API at all — `"read"` covers git clones only. Nothing is ever
pushed: a result saying pushes would be refused is expected and fine. Skip the
clone the result suggests; the read needs none.

If the attach is refused because a repository of the same name is already
attached - the fork itself, almost always - read through a helper session
instead (step 3a) and skip step 4. Any other refusal: relay its reason and stop.

## 3a. Read through a helper session (when the upstream cannot be attached)

A session checks every attached repository out at a directory named after it,
so the fork and its same-named upstream cannot share one. A helper session with
only the upstream attached does the read; this session never needs it attached.
Do every step in this turn, without asking the user: waiting for the helper and
archiving it are part of the skill.

1. Record the request and print the helper's first message:

   ```bash
   "${BASSTLER_PYTHON}" -m "${UPSTREAM_REVIEWS_HELPER_MODULE}" prompt \
     --upstream <upstream owner/name> --fork-owner <fork owner> \
     (--pull-request <number> | --branch <branch>) [--failure-logs]
   ```

   The message carries the program the helper runs - basstler's own
   `upstream_reviews_fetch`, code only - since a helper runs no code from
   repositories outside its session.
2. `mcp__claude-code-remote__create_session` with `source_url`
   `https://github.com/<upstream owner/name>`, `clone_depth: 1`,
   `model: "claude-haiku-5-5"`, `title: "basstler upstream-reviews helper"`,
   and the printed message, verbatim, as `prompt`.
3. Wait: run `sleep 30` as a background Bash command, and when it completes call
   `mcp__claude-code-remote__get_session` on the helper. Until its
   `status_bucket` is completed or failed, wait 15 seconds more the same way,
   for at most five minutes in all.
4. `mcp__claude-code-remote__list_events` on the helper with `kinds: ["user"]`
   and `limit: 10`. If that page holds no tool result, read the page before it
   (`before_id` set to its `first_id`), and so on.
5. Build the report from what those events brought into this session:

   ```bash
   "${BASSTLER_PYTHON}" -m "${UPSTREAM_REVIEWS_HELPER_MODULE}" report [--include-resolved]
   ```

   If it reports chunks missing, read the helper's earlier events and run it
   again. If the helper replied with an error instead, relay it.
6. `mcp__claude-code-remote__archive_session` on the helper, whatever the
   outcome, so it leaves nothing in the user's session list.

Then present the report as step 5 describes.

## 4. Read it

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

## 5. Present it

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
