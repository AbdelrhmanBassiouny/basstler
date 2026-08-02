---
name: stacked-pr-maintenance
description: Run one maintenance pass over a stacked-PR fork-staging workflow - close fork pull requests whose branch has landed upstream, reparent any orphaned child, restack branches whose parent moved, and promote every approved unblocked branch to the upstream review queue. Invoke as "/stacked-pr-maintenance [fork=<owner/repo>] [upstream=<owner/repo>] [--non-interactive]". Use when asked to run a stack maintenance pass, restack the stack, promote ready branches, or clean up landed fork pull requests, and when a scheduled routine hands this document its values.
allowed-tools: Bash, Read, Grep, AskUserQuestion, mcp__github__pull_request_read, mcp__github__list_pull_requests, mcp__github__update_pull_request, mcp__github__create_pull_request, mcp__github__issue_write, mcp__github__add_issue_comment, mcp__Gmail__create_draft
---

# Stacked-PR maintenance

You maintain a stacked-PR fork-staging workflow. The **fork** holds the full stack; the **upstream** is
the slow review queue. GitHub is the source of truth: a fork pull request's base branch is its parent,
the draft flag is the ready gate, the in-review label means promoted-to-upstream, and a branch that is
an ancestor of the upstream base has landed.

**Your job, and only this**: close fork pull requests whose branch has landed (phase 1), restack
branches whose parent moved (phase 2), promote every approved unblocked branch (phase 3), and react to
your own restacks' CI. It is *not* your job to do code review, or to read, answer, resolve or act on
the developer's review comments, or to make code changes addressing review feedback - that is the
developer's own session's work. Leave review threads untouched. The only code changes you make are
conflict resolution while restacking, and narrow fixes to CI failures your own restack caused.

Do not use the Workflow tool. Use plain git plus the GitHub MCP server. Never force-push a branch that
has an open upstream pull request unless it carries the rebase label.

HARD RULES so you never drift into review work:
- NEVER call `subscribe_pr_activity`, and never stay subscribed - you learn CI by POLLING (phase 2/step 0).
- If a review, review-comment, issue-comment, or any `<github-webhook-activity>` event is ever delivered
  to you, your ONLY valid action is to END THE TURN immediately: do not investigate it, do not draft or
  post a plan, do not reply, do not ask the developer to confirm anything. The one exception is a CI/check
  *status* you were polling for your own restack.
- NEVER enter plan mode or post a "here's my plan" comment. You either perform a mechanical step from the
  phases below or you stop; you never open a discussion.
- LABELS ARE REPLACE, NOT ADD: the GitHub label-write call takes the PR's **entire** new label set - it
  does not add to what's already there. Never compute that set yourself; `stack.py labels` computes it
  from the labels the PR carries now, and its output is the whole list you pass to the write.

## Step 0 - resolve which repositories this runs on

Nothing below names a repository or a remote. Resolve both here, once, and use what you get for the
whole run. Do not inspect, guess at, or rename remotes yourself - a remote's name carries no meaning,
and a wrong guess points every push at the wrong repository.

**a. Make the tooling present rather than assuming it.** Every phase shells out to
`.claude/stack/stack.py`, and a phase 2 failure lands after phase 1 has already mutated pull requests.
If `ls .claude/stack/stack.py` fails, `git fetch` the ref you were told to resolve this document from
and `git checkout <ref> -- .claude/stack/`. Once `.claude/stack/` is on the default branch this is a
no-op on a fresh clone.

**b. Take the fork and the upstream in this order, stopping at the first that answers:**

1. **What you were given.** `fork=<owner/repo>` and `upstream=<owner/repo>` in this skill's arguments
   are authoritative. Pass them straight through as `--fork` / `--upstream` and never second-guess them.
2. **What the checkout knows.** Run `python .claude/stack/stack.py configuration` (adding `--fork` /
   `--upstream` for anything you were given). It prints one `field<TAB>value` line per setting -
   `fork_remote`, `fork_repository`, `upstream_remote`, `upstream_repository`, `upstream_base`, the
   label names - deciding which remote is which by the repository each URL names. Exit 0 means use it.
   If an `upstream_setup_command` line appears, run exactly that command and re-run `configuration`.
3. **Exit status 4 - the fork could not be identified.** The checkout has no fork remote, or has more
   than one candidate, and there is no safe guess.
   - **If you were invoked with `--non-interactive`** (a scheduled routine always is): stop and report
     what `git remote -v` shows. Asking would break the hard rule against opening a discussion.
   - **Otherwise**: ask the developer with `AskUserQuestion`, offering the repositories from
     `git remote -v` as options, then persist the answer so the next run needs no question - write
     `fork_repository = "<owner/repo>"` into `.claude/personal/stack.toml` on the personal-notes branch:

     ```bash
     "${CLAUDE_PROJECT_DIR}/.claude/hooks/write-personal-notes-file.sh" \
       --source <the file you prepared> \
       --destination .claude/personal/stack.toml \
       --message "record which repository is my fork"
     ```

     That branch is fetched by every run, so the answer survives the fresh clone a scheduled run starts
     from. Re-run `configuration` and continue.

Any other non-zero exit is a stop-and-report, not something to work around.

## Step 1 - update fork main first

Before anything else. Every diff against the upstream base is measured from the fork's copy of it, so a
stale one inflates every root branch's diff. That branch is a pristine mirror of the upstream trunk -
keep it that way, because root branches base on it and the restack merges it into them, so anything
added here flows into every branch and then into the upstream. Fast-forward it:

```bash
git fetch <upstream-remote> <upstream-base> \
  && git push <fork-remote> <upstream-remote>/<upstream-base>:<upstream-base>
```

This must be a fast-forward. If GitHub rejects it as non-fast-forward, stop and report - do not force.

## Step 2 - refresh the derived stack

`git fetch <fork-remote>`, then refresh `.claude/stack/board.json` from the fork's **open** pull
requests (number, head, base, isDraft, labels, and - for the board's chips - statusCheckRollup and
body) via the GitHub MCP, and run `python .claude/stack/stack.py status`. There is no live mode; state
comes from `board.json` plus git.

**CI is the validator - poll it, never subscribe.** When you need a branch's verdict, poll with
`pull_request_read` → `get_check_runs` / `get_status` and read only the success/failure conclusion.
Never run the ROS (coraplex/semantic_digital_twin) suites here. A subscription delivers human review
comments and review threads, not just CI, and turns on the per-event handler that makes you
investigate, plan and reply - which is exactly how a maintenance run turns into review work.

## Pre-flight - before every push, merge or restack, no exceptions

Never move commits from memory, and never judge the move yourself. Ask:

```bash
python .claude/stack/stack.py preflight \
  --action push --source <branch> --destination <branch> --destination-remote <fork-remote>
```

Exit 0 means the move is clear. Exit 5 means it must not be made, and every reason is on stderr: the
branch is not the one checked out, the refspec names different branches on each side, the destination
is not the fork, or the push would make a child branch an ancestor of its own parent - which GitHub
reads as a merged pull request and closes. Fix the cause and ask again; never push past a refusal.

Then say in one sentence what you are integrating and why it belongs on that destination.

Step 1's fast-forward is the one push this cannot check: it deliberately maps one ref onto another and
happens before the board exists, so it exits 3 rather than judging the move. GitHub's own
non-fast-forward rejection is what guards that push instead, which is why step 1 stops rather than
forcing.

## The board publishes itself

You do not render or redeploy the board. An Action in the separate board repository polls the fork and
republishes it every few minutes, so make your state changes and move on. Never render `board.html` or
redeploy an Artifact here.

## Phase 1 - landed parents: reparent, label, then close

The upstream always merges with a merge commit, so a landed branch is always an ancestor of the
upstream base. That git-ancestry test - not the pull request's open/closed state - is how you know a
branch actually landed, and it is what both commands here are derived from.

**BASE CHANGES GO THROUGH THE GITHUB MCP SERVER.** Retarget a base with the MCP `update_pull_request`
tool and nothing else. The same request issued as a raw `PATCH /repos/{owner}/{repo}/pulls/{number}`
with curl and `GH_TOKEN` is refused with `403 - Changing a pull request's base branch is not permitted
for this session type`, however the body is formed - the block is on that credential, not on the
operation, so retrying it or reshaping the request cannot get past it. If you see that 403 you used the
wrong client, so switch rather than report it as a stuck reparent. The stacks endpoints below are the
mirror image: they have no MCP tool, so they do need curl.

**Reparent every orphaned child first.** Run:

```bash
python .claude/stack/stack.py reparents
```

It prints one `branch<TAB>pr<TAB>current base<TAB>target base` line per open pull request whose base has
already landed - including a base whose own pull request was *closed* rather than merged, which is
absent from the board entirely and which nothing else in this phase would ever look at. Retarget each
one with `update_pull_request`. This is never optional and never cosmetic: a child left on a landed base
cannot reach the upstream base, and is closed outright the moment that base branch is deleted. The
inflated diff it shows is a symptom, not the problem.

**NATIVE-STACK MEMBERS.** Changing the base of a pull request that belongs to a GitHub stack fails with
`422 - Cannot change the base branch because the pull request is part of a stack`. This is a different
refusal from the 403 above with a different cure: the 422 is GitHub protecting the stack's structure,
and dissolving the stack clears it. A pull request is a stack member iff its REST JSON carries a
non-null `stack` object when fetched with the header `X-GitHub-Api-Version: 2026-03-10`; the stacks
endpoints are not in the GitHub MCP server, so call them with curl and `GH_TOKEN`, always with that
version header. For exactly those children the reparent becomes:

1. `GET /repos/{owner}/{repo}/stacks` and record the affected stack's full pull-request list, bottom to
   top. Do not proceed without the recorded list - dissolving is destructive and there is no undo.
2. `POST /repos/{owner}/{repo}/stacks/{number}/unstack` (no body) to dissolve it. There is no selective
   removal: this drops every open, draft and closed member, leaving merged ones in place.
3. `update_pull_request` each orphaned child's base, which succeeds once the stack is gone. The child
   keeps its number, its labels and its review thread - never close it and open a replacement, which
   loses all three for a base change that is available to you.
4. Restack normally (phase 2's local merge/rebase plus push).
5. Re-create the stack: `POST /repos/{owner}/{repo}/stacks` with `{"pull_requests": [...]}` - the
   recorded list minus landed and closed members, bottom to top - then `GET` it back and confirm every
   member reports the stack.

Do not fast-forward the landed base branch as a way around this. It moves the merge-base so the diff
looks right, but the child still targets a branch about to disappear - and when that base is a stack's
trunk, moving it desynchronises the stack's recorded `base.sha` from its real head. If any call in this
sequence fails or answers with something not described here, stop work on that stack, leave the rest
untouched, and report it: this is a preview API, so never improvise around it.

**For each open fork pull request whose branch has landed** - `python .claude/stack/stack.py landed`
prints one `branch<TAB>pr` line per branch, and the reparents above have already moved its children, so
none is ever orphaned:

- **Label it as landed.** Always add the `merged` label as the durable indicator, even when you then
  close it. Compute the set first:
  `python .claude/stack/stack.py labels --current <each current label> --add merged`.
- **Close it**, with a comment noting it merged into the upstream base. If you cannot close it, leave it
  open: the label already flags it and the developer will close it.
- **Never label or close a fork pull request whose work has not landed.** The ancestry test is the only
  condition, and it is the command's, not yours.

## Phase 2 - restack and validate

Run `python .claude/stack/stack.py restack-plan` for the bottom-up plan. For each entry whose parent
moved, integrate the parent using its `strategy` (merge is the default and needs no force-push; rebase
force-pushes with lease) **only if the merge is clean**, run pre-flight, then push. CI is the validator.

**Do not block on CI.** After pushing a branch, move on to the next independent branch and keep
restacking and promoting in parallel - never sit idle waiting on a twenty-minute run. Poll the checks of
the branches you pushed at the start of each pass, and react then.

When a branch conflicts or its CI comes back red, get around ROS as far as you can - never park a branch
on a ROS dependency:

- **If the failure lives in the ROS-free layer** (`krrood`, which runs here), reproduce it with a
  meaningful failing test (mimicking the offending pattern in the `krrood` test datasets per `AGENTS.md`
  when it originates in another package), fix it, validate by running the `krrood` suite locally, push,
  and let CI confirm end to end.
- **A generated `ormatic_interface.py` conflict never blocks** - the file is regenerated, not
  hand-authored, so never skip the branch or its descendants over it.
  - Package ORM (`{semantic_digital_twin,coraplex,experiments}/**/orm/ormatic_interface.py`) is rebuilt
    from source by CI's `Build ORM` step, so its committed content is throwaway: resolve by taking
    either side, push, and let CI regenerate and validate it.
  - The `krrood` dataset ORM (`test/krrood_test/dataset/ormatic_interface.py`) regenerates locally with
    no ROS: run the `krrood` suite, commit the regenerated file, and push.
  - Never hand-edit an `ormatic_interface.py`; only take a side or regenerate.
- **Everything else** - a real conflict, or CI-red that is neither ROS-only nor the throwaway ORM file -
  is not yours to resolve. Delegate it to the branch's owning session, never silently skip it:
  1. Find the session: search the fork pull request body for a `https://claude.ai/code/session_...` link.
  2. Post a comment on the fork pull request, prefixed `🔴 ROUTINE - NEEDS RESOLUTION:`, stating what you
     were doing, what happened (the conflicting files, or the failing check and its conclusion), and the
     ask - that they resolve and push, and you will pick the branch back up once it restacks clean. This
     comment is the only channel available to you; if that session is still subscribed to its own pull
     request, it arrives there as a live event rather than text sitting on GitHub.
  3. Label the pull request `needs-resolution` (via `stack.py labels`, so the rest of its labels survive)
     so the state is visible even if no session is listening, and so you never re-attempt the same
     failing restack every run.
  4. At the start of every phase 2 pass, fetch `mergeable_state` for each branch carrying
     `needs-resolution` (`pull_request_read` → `get`). Anything other than `dirty` means the conflict is
     resolved: clear the label and include the branch in the plan normally. Only keep it and skip the
     branch while `mergeable_state` is `dirty`.
  Record every branch you delegate - the finish summary must report it, since a delegated comment is not
  guaranteed to be seen.

Keep restacking and promoting the other branches while CI chews on the ones you pushed. Never disable a
leak or CI check to go green.

## Phase 3 - promote

Housekeeping first: remove any `cram2-link-sent` label from a fork pull request that is now `in-review`
or landed - its link has been acted on.

Collect what to promote: `python .claude/stack/stack.py next --porcelain` prints one `name<TAB>pr` line
per branch that is approved (un-drafted), whose parent has reached in-review or landed, and that is not
withheld by `needs-resolution`. There is no admission cap and no ordering beyond dependency order: every
such branch promotes in the same run. Skip any already carrying `cram2-link-sent` when deciding whether
to build a *new* link, but still process the others. If it prints nothing, promote nothing.

For each collected pull request:

1. **Try to open the upstream pull request directly** via the GitHub MCP - base the upstream base, head
   `<fork owner>:<branch>`, with a filled title and description. If it succeeds, add `in-review` to the
   fork pull request and you are done with that branch.
2. **If opening it fails** (the usual case - the GitHub app has no write access to the upstream), build
   the compare-and-create link:

   ```bash
   python .claude/stack/stack.py promotion-link \
     --branch <branch> --title <title> --body <one paragraph plus a link back to the fork PR>
   ```

   It owns the URL encoding and the length limit, so the prefill cannot be silently lost - keep the body
   short anyway, and note that it warns on stderr when it had to shorten one. Collect the link and add
   `cram2-link-sent` so later runs do not rebuild it. Do **not** add `in-review`: the upstream pull
   request is not open until the developer clicks Create, and they add the label then.

## Finish

The **top** of the finish summary must list all pending upstream create-links: any built this run, and
any fork pull request still carrying `cram2-link-sent` but not yet `in-review` (re-listed from prior
runs, its link rebuilt with `promotion-link`). This section appears at the top even when nothing new was
built, as long as any are pending - a scheduled run is configured to email its summary, so the summary
*is* the delivery. List each pull request's number, title, branch and one-click link. Set
`cram2-link-sent` only on newly built links.

The Gmail connector can only draft, not send, so never rely on it for delivery; a `create_draft` copy is
optional and lands unsent.

Right after the links, list every branch you **delegated** this run: its number and branch, the
conflicting files or failing check, the session link you addressed (or that the body had none), and a
link to the comment you posted. Then list every pull request whose phase 1 reparent you could **not**
complete: its number, the base it is stuck on, the base it should have, and which step of the
native-stack sequence stopped you - a stack left dissolved or half-rebuilt needs attention immediately
and nothing else surfaces it. Then summarise what you closed, restacked and promoted, and anything you
stopped on.
