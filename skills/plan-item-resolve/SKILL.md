---
name: plan-item-resolve
description: Resolve what stalls an underway plan item - conflicts, CI, review threads, tracking-issue discussion - on its existing branch, per the execution mode. Invoke as "/plan-item-resolve <plan-id> <item-id>" or "/plan-item-resolve <pull-request-number>". Use from a dashboard's Resolve/Resume/Reconsider link or when asked to resolve, unblock or resume an item.
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, AskUserQuestion, Skill, EnterPlanMode, ExitPlanMode, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__issue_read, mcp__github__get_file_contents, mcp__github__update_pull_request, mcp__Claude_Code_Remote__subscribe_pr_activity
---

# Plan Item Resolve

Generic, plan-agnostic — nothing here may hardcode a specific plan id,
item, or branch. Unlike `plan-item-kickoff` (for an item that hasn't
started), this skill is for an item that already has real state - a
branch, a PR, prior review, a recorded blocker - and needs that state
understood before deciding what to do next. A pull request no plan tracks is
resolved the same way; see *Untracked pull requests* below for what changes.

**Step 1 is research only — apart from the stack pass it starts with, it creates
nothing and writes no code.**
Step 2 resolves the item's execution mode, and that mode decides what
happens next: `plan` presents the plan and stops until the user approves it,
`auto` carries it out on the item's existing branch without asking, and
`ask` puts the choice to the user. [`execution-modes.md`](../plan-dashboard/execution-modes.md) states what
each mode means and what it still obliges.

This skill never creates a branch or a pull request — the item already has
both, and an item that has neither belongs to `plan-item-kickoff`. Every
invocation starts fresh in the current session; it does not try to detect or
resume any other session.

## 1. Gather the item's context

Follow [`plan-item-gathering.md`](../plan-dashboard/plan-item-gathering.md) end to end — the setup check, the
item's resolution off the personal-notes branch, the tracking-issue
subscription, its recorded state, the plan's standing rules, the dependency
chain, and the standing conventions. `plan-item-kickoff` runs the same
procedure, which is why it lives there rather than in either skill.

Then add the part only a resolve needs — **the live state of work that
already exists**, which is where the cause of a stall almost always is:

- If `pull_request_number` is set: fetch the PR (`mcp__github__pull_request_read`,
  `method: "get"`) for its mergeable state and CI status
  (`method: "get_check_runs"`), then its review threads
  (`method: "get_review_comments"`) and plain comments
  (`method: "get_comments"`) — read every one, not just the most recent,
  since an older unresolved thread is exactly the kind of thing this skill
  exists to surface. A failing check or a requested-changes review is
  usually the actual blocker; state exactly which one and why, don't just
  say "CI is failing."
- If the item has a `branch`, invoke `/upstream-reviews` for it and read every
  unresolved thread it reports — always, whatever state the fork PR is in. The
  branch may also have a pull request on the upstream, whose review threads
  none of the calls above can see, and a fork PR can look entirely clean while
  the item is in fact stalled on an upstream request for changes. Nothing this
  session can read tells it whether that upstream pull request exists — its
  GitHub scope is the fork alone, and the label recording the promotion can be
  missing while the upstream pull request exists, so its absence is no evidence.
  `/upstream-reviews`
  settles it where the read is permitted, and reports a branch with no upstream
  pull request as a clean answer, so a pre-check would buy nothing and skip the
  case this bullet exists to catch. If the dispatch or the run fails, don't let
  that fail the skill: mention it when drafting the plan (step 3) and
  continue — upstream state is valuable context, not a precondition.
- If the item has no PR yet (e.g. blocked before ever starting): there is
  no PR-side state to check — rely on `blockers`/`notes` and the tracking
  issue instead.
- If the plan has a `tracking_issue`, fetch its comments
  (`mcp__github__issue_read`, `method: "get_comments"`) and read every one
  that mentions this item by id, branch, or title — a structural change
  proposed there (a dependency change, a scope split) can be exactly why
  an item stalled.
- If a branch or PR exists, read what's actually in it
  (`mcp__github__pull_request_read` for the diff/description,
  `mcp__github__get_file_contents` or a local `git fetch` + `git show` for
  the real file contents) before proposing anything — the plan must resolve
  the real, current state, not a guessed one. When the resolution involves
  matching an established pattern (e.g. a review comment asking this item to
  follow what a later pull request already settled on), read the merged pull
  requests that last changed the same files, the way `plan-item-kickoff`
  does.

## 2. Resolve how this item gets resolved

Follow [`execution-modes.md`](../plan-dashboard/execution-modes.md): run its `resolve --skill resolve`
call, and if the answer is `ask`, put its question — with a recommendation
drawn from what step 1 just turned up, and the reasons behind it.

Do this only once step 1 is done. What decides the recommendation here
is whether the cause of the stall is actually identified: a named failing
check or review comment with an obvious fix argues for going ahead, and a
blocker whose real cause is still a guess argues for planning first.

Pass `--requested <mode>` when the user named a mode in the invocation
itself.

## 3. Draft the plan

First record what you found, per [`manifest-staleness.md`](../plan-dashboard/manifest-staleness.md): the real blocker in
`blockers`, and `status` when it is wrong (`blocked`, `deferred`). `notes` change only when
what the item means changes.

Apply [`plan-item-gathering.md`](../plan-dashboard/plan-item-gathering.md)'s last section first: anything you
are about to raise as an open question is very often already answered by the
material step 1 gathered — here including the pull request's own review
threads and the tracking issue's discussion.

Also ask whether the item should still exist separately: follow
[`scope-decision.md`](../add-plan-item/scope-decision.md). If nothing substantial would remain once the
overlapping edits are removed, folding it into that item is often the
resolution — an item stuck behind its own parent is sometimes stuck because it
was never really a separate item. The same goes when two items turn out to have
built the same thing, which that document's purpose comparison is there to
catch.

Draft a concrete plan to resolve the item: what's actually wrong (cite the
specific failing check, review comment, unresolved upstream review thread,
blocker text, or regressed dependency that's the real cause — never a vague
"something's blocking this"), what changes it requires, in which files, in
what order, and how each part will be verified. Cite where each part of the
plan came from so it can be sanity-checked against the source. Flag
explicitly, never silently paper over:

- Any dependency that regressed or still isn't safe to build on.
- Any conflict between what `blockers`/`notes` says and what the PR's own
  review threads or the tracking issue actually say.
- Any conflict between the fork PR's state and the upstream review: a fork
  PR that is green and out of draft while its upstream pull request has
  unresolved threads is exactly the stall this skill exists to surface.
- Whether upstream review state was read at all, when the item has a branch
  but `/upstream-reviews` could not be run.
- Anything genuinely unresolved after the check above — say so rather
  than filling the gap with an assumption.

In `plan` mode, present it via `ExitPlanMode` and stop there — nothing below
happens until the user approves it, and whether to carry the approved plan
out in this session or a fresh one is their call. In `auto` mode, don't ask:
the plan is settled the moment it is drafted, and the flags above go into
the record described below instead of into a question.

Either way, write no code in this step — its only output is the plan itself.

## 4. Carry it out — `auto` mode only

Work the plan on the item's existing branch, honoring the standing
conventions step 1 cross-checked: tests first per TDD, commits in the user's
own git identity, no assistant author or co-author trailer.

[`execution-modes.md`](../plan-dashboard/execution-modes.md) states what stays owed while doing it, and the
bar for stopping to ask anyway. Two things are this skill's own, because the
item is already underway rather than being started:

- **The record is an update, not a first draft.** Rewrite the item's
  `blockers`, `notes` and `status` to say what is true now - replacing a
  blocker whose recorded cause turned out to be wrong rather than adding to
  it - and refresh the PR-progress note and the pull request description the
  same way. What the resolution was, and why, belongs in the pull request,
  not in `roadmap.md`; add a roadmap entry only for a rule every later item
  must follow. Then republish the dashboard with `/plan-dashboard`.
- **The pull request goes back to draft after the push**, per the user's own
  convention, unless they marked it ready themselves — in which case the
  item was finished and this skill should not have been resolving it.

Once the fix is pushed, carry it into the pull requests stacked on this item's
branch, which a resolve otherwise leaves holding the state it replaced — follow
[`propagating-a-fix.md`](./propagating-a-fix.md).

Finish by reporting what was wrong, what was changed, and what was decided —
in `auto` mode this report is the user's first look at the resolution.

## Untracked pull requests

When invoked with a pull request number whose branch no plan tracks, resolve
the pull request itself. Every step above runs, with these differences:

- **Step 1** skips the plan-reading parts [`plan-item-gathering.md`](../plan-dashboard/plan-item-gathering.md)
  names, and the tracking-issue bullet above. Everything about the pull
  request's live state - checks, review threads, comments, `/upstream-reviews`,
  the diff - is read exactly as for a tracked item, and the branch's
  PR-progress note on the personal-notes branch, if it has one, stands in for
  the item's `notes`.
- **Step 3** also asks whether the pull request belongs in a plan: run
  [`scope-decision.md`](../add-plan-item/scope-decision.md) against the existing plans. If one fits, say
  which and why, and offer `/add-plan-item` rather than adding it unasked.
- **Step 4**'s record is the PR-progress note and the pull request
  description; there is no `plan.yaml` entry or dashboard to update.
