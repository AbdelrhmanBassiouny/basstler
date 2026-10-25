---
name: stacked-pr-maintenance
description: Run one maintenance pass over a stacked-PR fork-staging workflow - reparent any pull request whose base has landed, restack branches whose parent moved, and promote every approved unblocked branch to the upstream review queue. Invoke as "/stacked-pr-maintenance [fork=<owner/repo>] [upstream=<owner/repo>]". Use when asked to run a stack maintenance pass, restack the stack, promote ready branches,, or clean up after a branch has landed upstream, and as the first step of plan-item-kickoff and plan-item-resolve.
allowed-tools: Bash, Read, Grep, AskUserQuestion, mcp__github__pull_request_read, mcp__github__list_pull_requests, mcp__github__update_pull_request, mcp__github__issue_write, mcp__github__add_issue_comment
---

# Stacked-PR maintenance

You maintain a stacked-PR fork-staging workflow. The **fork** holds the full stack; the **upstream**
is the slow review queue. GitHub is the source of truth:

- a fork pull request's **base branch is its parent** in the stack;
- a fork pull request stays a **draft until its author has reviewed it themselves**, so taking it out
  of draft is the author's sign-off and the only signal that it may be promoted - that is all "the
  draft flag is the ready gate" means, and nothing else grants approval;
- the **in-review label** means the branch has been promoted to the upstream;
- a branch that is an **ancestor of the upstream base** has landed.

**Your job, and only this**: reparent any pull request whose base has landed, close what has
landed by fast-forwarding, restack branches whose parent moved, promote every approved unblocked
branch, and report what you did. The steps below are that job, in order.

It is *not* your job to do code review, to read, answer, resolve or act on the developer's review
comments, or to make code changes addressing review feedback - that is the developer's own
session's work. Leave review threads untouched.

**You do not write code, and you change no files at all** - not even to resolve a conflict. Every
branch in this stack belongs to somebody else, so a conflict is reported to its owner and left
exactly where it is.

Do not use the Workflow tool - the multi-agent orchestration tool that fans work out to subagents.
This pass is a short sequence of git and API calls; fanning it out multiplies the chance of two
agents pushing the same branch. Use plain git plus the GitHub MCP server. Never force-push a branch
that has an open upstream pull request unless it carries the `rebase` label. The executor's own
restack is the one exception: it replaces the merges earlier passes left at a branch's tip with a
single new one, under a lease, so a branch carries one restack merge however many passes it waits
through.

HARD RULES so you never drift into review work:
- NEVER call `subscribe_pr_activity`, and never stay subscribed - you learn CI by POLLING (step 2).
- If a review, review-comment, issue-comment, or any `<github-webhook-activity>` event is ever delivered
  to you, your ONLY valid action is to END THE TURN immediately: do not investigate it, do not draft or
  post a plan, do not reply, do not ask the developer to confirm anything. The one exception is a CI/check
  *status* you were polling for your own restack.
- NEVER enter plan mode or post a "here's my plan" comment. You either perform a mechanical step from the
  steps below or you stop; you never open a discussion.
- LABELS ARE REPLACE, NOT ADD: the GitHub label-write call takes the PR's **entire** new label set - it
  does not add to what's already there. Never compute that set yourself; `basstler.stack labels` computes it
  from the labels the PR carries now, and its output is the whole list you pass to the write.

## Step 0 - resolve which repositories this runs on

Nothing below names a repository or a remote. Resolve both here, once, and use what you get for the
whole run. Do not inspect, guess at, or rename remotes yourself - a remote's name carries no meaning,
and a wrong guess points every push at the wrong repository.

**a. Source the configuration once.** The tooling is the plugin's and the package's, never the
checkout's, so nothing has to be restored into the working tree whichever branch it has checked
out; every command below runs the package through the interpreter the configuration names:

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
```

Once `basstler/` is on the default branch this is a no-op on a fresh clone. The pass itself no
longer takes the tooling away: `restack` switches branches in a worktree of its own, so the checkout
you invoked it from keeps its branch and its files.

**b. Take the fork and the upstream in this order, stopping at the first that answers:**

1. **What you were given.** `fork=<owner/repo>` and `upstream=<owner/repo>` in this skill's arguments
   are authoritative. Pass them straight through as `--fork` / `--upstream` and never second-guess
   them.
2. **What the checkout knows.** Run `"${BASSTLER_PYTHON}" -m basstler.stack configuration` (adding `--fork` /
   `--upstream` for anything you were given). It prints one `field<TAB>value` line per setting -
   `fork_remote`, `fork_repository`, `upstream_remote`, `upstream_repository`, `upstream_base`, the
   label names - deciding which remote is which by the repository each URL names. Exit 0 means use
   it. If an `upstream_setup_command` line appears, run exactly that command and re-run
   `configuration`.
3. **Exit status 4 - the fork could not be identified.** The checkout has no fork remote, or has more
   than one candidate, and there is no safe guess. Ask the developer with `AskUserQuestion`,
   offering the repositories from `git remote -v` as options, then persist the answer so the next
   run needs no question - write `fork_repository = "<owner/repo>"` into
   `.claude/personal/stack.toml` on the personal-notes branch:

   ```bash
   "${BASSTLER_PLUGIN_ROOT}/hooks/write-personal-notes-file.sh" \
     --source <the file you prepared> \
     --destination .claude/personal/stack.toml \
     --message "record which repository is my fork"
   ```

   That branch is fetched by every run, so the answer survives a fresh clone. Re-run
   `configuration` and continue.

4. **Exit status 11 - the project names no upstream.** Ask the developer for the `<owner>/<name>`
   the project is reviewed on, save it with `"${BASSTLER_PYTHON}" -m basstler.setup.steps
   configure-upstream --repository <owner>/<name>`, re-run `configuration` and continue.

Any other non-zero exit is a stop-and-report, not something to work around.

## Step 1 - reparent every orphaned child, before anything moves

Do this first, and before step 2. Retargeting a pull request whose base has landed is what lets the
next step finish it, and a child left on a landed base cannot reach the upstream base at all - it is
closed outright the moment that base branch is deleted. The inflated diff such a child shows is a
symptom, not the problem.

**BASE CHANGES GO THROUGH THE GITHUB MCP SERVER.** Retarget a base with the MCP `update_pull_request`
tool and nothing else. The same request issued as a raw `PATCH /repos/{owner}/{repo}/pulls/{number}`
with curl and `GH_TOKEN` is refused with
`403 - Changing a pull request's base branch is not permitted for this session type`, however the
body is formed - the block is on that credential, not on the operation, so retrying it or reshaping
the request cannot get past it. If you see that 403 you
used the wrong client, so switch rather than report it as a stuck reparent. The stacks endpoints
below are the mirror image: they have no MCP tool, so they do need curl.

Export the board first - every step below derives from it, and this one is no exception:

```bash
"${BASSTLER_PYTHON}" -m basstler.maintenance board --write
```

Never assemble that file by hand - a fetch that drops a field produces a board that is wrong rather
than obviously incomplete.

Then run:

```bash
"${BASSTLER_PYTHON}" -m basstler.stack reparents
```

It prints one `branch<TAB>pr<TAB>current base<TAB>target base` line per open pull request whose base
has already landed - decided by git ancestry, so it also covers a base whose own pull request was
*closed* rather than merged, which is absent from the board entirely and which nothing else would
ever look at. Retarget each one with `update_pull_request`.

**NATIVE-STACK MEMBERS.** Changing the base of a pull request that belongs to a GitHub stack fails
with `422 - Cannot change the base branch because the pull request is part of a stack`. This is a
different refusal from the 403 above with a different cure: the 422 is GitHub protecting the stack's
structure, and dissolving the stack clears it. A pull request is a stack member iff its REST JSON
carries a non-null `stack` object when fetched with the header `X-GitHub-Api-Version: 2026-03-10`;
the stacks endpoints are not in the GitHub MCP server, so call them with curl and `GH_TOKEN`, always
with that version header. For exactly those children the reparent becomes:

1. `GET /repos/{owner}/{repo}/stacks` and record the affected stack's full pull-request list, bottom
   to top. Do not proceed without the recorded list - dissolving is destructive and there is no undo.
2. `POST /repos/{owner}/{repo}/stacks/{number}/unstack` (no body) to dissolve it. There is no
   selective removal: this drops every open, draft and closed member, leaving merged ones in place.
3. `update_pull_request` each orphaned child's base, which succeeds once the stack is gone. The child
   keeps its number, its labels and its review thread - never close it and open a replacement, which
   loses all three for a base change that is available to you.
4. Restack normally (step 2's local merge/rebase plus push).
5. Re-create the stack: `POST /repos/{owner}/{repo}/stacks` with `{"pull_requests": [...]}` - the
   recorded list minus landed and closed members, bottom to top - then `GET` it back and confirm
   every member reports the stack.

Do not fast-forward the landed base branch as a way around this. It moves the merge-base so the diff
looks right, but the child still targets a branch about to disappear - and when that base is a
stack's trunk, moving it desynchronises the stack's recorded `base.sha` from its real head. If any
call in this sequence fails or answers with something not described here, stop work on that stack,
leave the rest untouched, and report it: this is a preview API, so never improvise around it.

## Step 2 - run the pass

The rest of the pass is one command:

```bash
"${BASSTLER_PYTHON}" -m basstler.maintenance run-report
```

It performs the fast-forward, the restack and the promotion, and prints the finish summary as
markdown, with titles and links already filled in. Do not re-derive any of it, do not fetch the
pull requests to look up their titles, and do not run the individual commands as well - that does
the same work twice. `--json` prints the same run as one machine-readable document instead, for
tooling; a session never needs it.

**Act on the status, which the summary leads with and the process exits with:**

| status | what you do |
|---|---|
| `success` | render the summary |
| `not-fast-forward` | report it - the fork's base is behind the upstream, which every branch is measured against |
| `move-refused` | stop and look; the reasons are in the document |
| `branch-needs-attention` | carry every branch it names into the summary |

A non-zero run also prints its status in words, so you never have to look a number up.

**Then read what it left you.** `reparents` is the only entry that asks anything of you: a base
change is the one write this credential is refused, so step 1 of the next pass is where it gets
made. Everything else - `fast_forward`, `landed`, `restacked`, `promoted`,
`promotion_labels_cleared` - is what happened, for the summary. A `restacked` entry other than
`pushed` or `up-to-date` is a branch the pass could not publish; the executor has already labelled
and commented on it, so name it in the summary and move on.

A `skipped` entry is a pull request open on the fork whose head the pass cannot maintain, so it was
left out of the restack, the promotion and the landed list, and nothing was labelled or commented on
it. Its `pull_request` is the board's entry for it, and its `reason` says why it was skipped:
`head-on-another-fork` - the head lives on another contributor's fork (`head_repository` names it), which this credential cannot push to - or `head-repository-deleted` -
the repository its head lived in is gone. Its base is still on the fork, so step 1 still reparents it
when that base lands. List it in the summary as skipped, with its reason; it is not yours to fix.

The one exception is `integration-failed`: integrating the parent failed without conflicting on
anything, so the branch is not what needs fixing and its owner was deliberately not told. Its
`explanation` carries what git said - an untracked file in the way, unrelated histories, a
reference that does not resolve. That is the pass's own environment to fix, so report it in the
summary as yours rather than the branch owner's, and never label the branch for it.

If a landed pull request is somehow still open after the pass, report it rather than closing it
yourself.

## What this pass never does

- **It never resolves a conflict** - not the executor, and not you. A conflict is a change to
  somebody else's branch, so it is reported to its owner and left exactly where it is.
- **It never opens the upstream pull request.** Do not attempt that call: promotion builds the
  compare-and-create link and stops there, and the developer clicks Create.
- **It never debugs or fixes a red check.** Report it to the branch's owner the same way a conflict
  is reported: find the session link in the fork pull request's description, post a comment prefixed
  `🔴 MAINTENANCE - NEEDS RESOLUTION:` stating the failing check and its conclusion, and label the pull
  request `needs-resolution` via `basstler.stack labels` so the rest of its labels survive. That comment is
  the only channel available to you: no session subscribes to a pull request's activity, so it sits
  on GitHub until the owner reads it - write it to stand alone. Never disable a check to go green.
- **It never subscribes to learn CI.** Poll with `pull_request_read` → `get_check_runs` /
  `get_status` and read only the success/failure conclusion. A subscription delivers human review
  comments and review threads, not just CI, and turns on the per-event handler that makes you
  investigate, plan and reply - which is exactly how a maintenance run turns into review work.
- **It never blocks on CI.** Poll the checks of the branches pushed at the start of each pass and
  react then; do not sit idle waiting on a long run.
- **It never adds `in-review`.** That is the developer's, once they have clicked Create.

## Finish

Relay `run-report`'s summary as it printed it. Add only what the session did itself, which the
executor cannot know:

- every pull request whose reparent in step 1 could **not** be completed: its number, the base it is
  stuck on, the base it should have, and which step of the native-stack sequence stopped you - a
  stack left dissolved or half-rebuilt needs attention immediately and nothing else surfaces it;
- every failing check you reported, with the comment's link;
- anything you stopped on.

## Command reference - resuming a partial run

Step 2 performs all of these in order. Reach for one directly only when a run stopped partway, or
when a single step has to be re-run:

```bash
"${BASSTLER_PYTHON}" -m basstler.maintenance board --write   # export the fork's open pull requests
"${BASSTLER_PYTHON}" -m basstler.maintenance fast-forward    # move the fork's base onto the upstream
"${BASSTLER_PYTHON}" -m basstler.maintenance restack         # integrate every moved parent, publish, report
"${BASSTLER_PYTHON}" -m basstler.maintenance promote         # build and record every upstream link
```

Each prints what it did and exits with the same statuses as the whole pass. Run `--help` for a
command's own flags rather than looking them up here.

`run-report` deletes the board when it finishes, so a resumed run starts by exporting a fresh one.

### Checking a move you make by hand

Never move commits from memory, and never judge the move yourself. The executor checks every push
it makes; you invoke this only for a push you are making yourself:

```bash
"${BASSTLER_PYTHON}" -m basstler.stack check-move \
  --action push --source <branch> --destination <branch> --destination-remote <fork-remote>
```

Exit 0 means the move is clear. Exit 5 means it must not be made, and every reason is on stderr.
Fix the cause and ask again; never push past a refusal.
