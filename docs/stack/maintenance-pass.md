# The maintenance pass: why its rules hold

`plugin/skills/stacked-pr-maintenance/SKILL.md` carries only the steps a pass takes. This page is
the reasoning behind them, for whoever changes the skill or the executor. The workflow itself is in
[README.md](README.md).

## What GitHub records, and what the pass reads from it

- A fork pull request's base branch is its parent in the stack.
- A fork pull request stays a draft until its author has reviewed it; taking it out of draft is the
  only signal that it may be promoted. Nothing else grants approval.
- The `in-review` label means the branch was promoted. Only the developer adds it, once they have
  clicked Create on the upstream link.
- A branch that is an ancestor of the upstream base has landed.

## Why the pass never touches code or reviews

Every branch in the stack belongs to somebody else's session. A conflict resolved by the pass is a
change to that branch its owner never saw, so a conflict is reported to its owner and left exactly
where it is. Review threads are the owner's work for the same reason.

A pull request activity subscription delivers review comments and threads, not just CI, and turns on
the per-event handler that makes a session investigate, plan and reply - which is how a maintenance
run turns into review work. So CI is learned by polling, and a review event that reaches the pass
ends its turn.

The Workflow tool fans work out to subagents; for a short sequence of git and API calls that only
multiplies the chance of two agents pushing the same branch.

## Why reparenting comes first

A child left on a landed base cannot reach the upstream base, and is closed outright the moment
that base branch is deleted. The inflated diff it shows is a symptom, not the problem. Retargeting
it is what lets the fast-forward finish it.

`reparents` decides by git ancestry, so it also covers a base whose own pull request was *closed*
rather than merged - one absent from the board entirely.

### The 403: base changes go through the MCP server

A raw `PATCH /repos/{owner}/{repo}/pulls/{number}` with curl and `GH_TOKEN` is refused with
`403 - Changing a pull request's base branch is not permitted for this session type`, however the
body is formed. The block is on that credential, not on the operation, so retrying or reshaping the
request cannot get past it; the MCP `update_pull_request` tool can. It is also why the executor
never makes a base change itself and leaves `reparents` to the next pass's step 1.

### The 422: native stacks

Changing the base of a pull request in a GitHub stack fails with
`422 - Cannot change the base branch because the pull request is part of a stack`. That is GitHub
protecting the stack's structure, and dissolving the stack clears it. A pull request is a member
when its REST JSON, fetched with `X-GitHub-Api-Version: 2026-03-10`, carries a non-null `stack`
object. The stacks endpoints have no MCP tool, so they need curl.

Unstacking has no selective form: it drops every open, draft and closed member and keeps merged
ones, and there is no undo - hence recording the list first. Closing the child and opening a
replacement would lose its number, labels and review thread for a base change that is available.
Fast-forwarding the landed base instead moves the merge-base so the diff looks right, but the child
still targets a branch about to disappear, and when that base is a stack's trunk it desynchronises
the stack's recorded `base.sha` from its real head. The API is a preview, so the pass never
improvises around an answer it does not recognise.

## Why the pass trusts the executor's output

`run-report` already fills titles and links into the summary. Re-deriving them, or running the
individual commands as well, does the same work twice and can disagree with what actually ran.
`--json` exists for tooling; a session never needs it.

`integration-failed` means integrating the parent failed without conflicting on anything - an
untracked file in the way, unrelated histories, a reference that does not resolve. The branch is not
what needs fixing, so its owner is deliberately not told and it is never labelled.

A `skipped` pull request has a head the credential cannot push to (`head-on-another-fork`) or one
whose repository is gone (`head-repository-deleted`). Its base is still on the fork, so step 1 still
reparents it when that base lands.

## Labels replace

GitHub's label write takes the pull request's entire new label set. Computing that set from the
intended change alone silently strips the rest, so `basstler.stack labels` computes it from the
labels the pull request carries now.

## Force-pushes

A branch with an open upstream pull request is never force-pushed unless it carries `rebase`. The
executor's restack is the one exception: it replaces the merges earlier passes left at a branch's
tip - only those carrying its `Restacked-parent:` and `Restacked-parent-commit:` trailers, never a
merge made by hand - with a single new one, under a lease - see
[One restack merge per branch](README.md#one-restack-merge-per-branch).

## Reporting a red check

No session subscribes to a pull request's activity, so the `🔴 MAINTENANCE - NEEDS RESOLUTION:`
comment sits on GitHub until the owner reads it; it has to stand alone. The `needs-resolution` label
withholds the branch from promotion until it is cleared.
