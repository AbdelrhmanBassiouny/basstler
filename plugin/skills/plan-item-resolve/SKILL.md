---
name: plan-item-resolve
description: Gather everything available about one already-underway tracked plan item (its plan.yaml entry, roadmap.md history, the real state of its branch/PR - conflicts, CI, review comments - and any relevant discussion on its plan's tracking issue), then resolve whatever is stalling it in whichever execution mode is in force - presenting a plan for approval, carrying it out directly on the item's existing branch, or asking which. Invoke as "/plan-item-resolve <plan-id> <item-id>". Use when resolving a blocked, in-progress, or deferred item from a plan-dashboard's "Resolve"/"Resume"/"Reconsider" link, or when the user asks to "resolve", "unblock", "resume", or "reconsider" a specific tracked item.
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, AskUserQuestion, Skill, EnterPlanMode, ExitPlanMode, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__issue_read, mcp__github__get_file_contents, mcp__github__update_pull_request, mcp__Claude_Code_Remote__subscribe_pr_activity
---

# Plan Item Resolve

Generic, plan-agnostic — nothing here may hardcode a specific plan id,
item, or branch. Unlike `plan-item-kickoff` (for an item that hasn't
started), this skill is for an item that already has real state - a
branch, a PR, prior review, a recorded blocker - and needs that state
understood before deciding what to do next.

**Steps 1-4 are research only — they create nothing and write no code.**
Step 5 resolves the item's execution mode, and that mode decides what
happens next: `plan` presents the plan and stops until the user approves it,
`auto` carries it out on the item's existing branch without asking, and
`ask` puts the choice to the user. `${EXECUTION_MODES_DOCUMENT}` states what
each mode means and what it still obliges.

This skill never creates a branch or a pull request — the item already has
both, and an item that has neither belongs to `plan-item-kickoff`. Every
invocation starts fresh in the current session; it does not try to detect or
resume any other session.

## 0. Check the setup is in place, and offer it if not

The item's manifest entry and roadmap live on the personal-notes branch, which
the user may not have set up yet. Follow
`.claude/skills/setup-personal-notes/prerequisite-check.md` before step 1: run
the check, and if it reports anything missing, offer `/setup-personal-notes`
rather than failing on a branch that isn't there.

## 1. Resolve the item

Source the shared config script — it resolves the personal-notes
remote/branch precedence and defines `DEPENDENCY_READINESS_DOCUMENT` (used in
step 2):

```bash
source .claude/hooks/resolve-personal-notes-config.sh
git fetch "${NOTES_REMOTE}" "${NOTES_BRANCH}" --quiet
```

Load `<plan-id>/plan.yaml` + `roadmap.md` off `FETCH_HEAD` (same resolution
`plan-dashboard`'s own step 1 uses — read `resolve-personal-notes-config.sh`
if the precedence is unclear rather than re-deriving it). Find the item by
`id` (or `branch` if `id` is unset) among `items[]`.

If the plan id or item id doesn't resolve, stop and list what's actually
available (every plan id under `plans/*/plan.yaml`, or every item id in the
named plan) rather than guessing which one was meant.

If the plan has a `tracking_issue`, subscribe to it now via
`mcp__Claude_Code_Remote__subscribe_pr_activity` (it takes a plain issue
number the same way it takes a PR number). A resolve session may go on to
push a fix directly, without a fresh session ever starting - the
subscription `session-start.sh` sets up for an already-checked-out item
branch never fires in that case - so subscribing here, before gathering any
state, is what actually covers a resolve that turns into an uninterrupted
fix. Skip this step entirely if the plan has no `tracking_issue`. The call
is idempotent, so it's safe to run even if something already subscribed
this session. If it errors, don't let that fail the skill: mention it in
passing when presenting the plan (step 5) and continue - subscribing is a
convenience for staying aware of concurrent structural changes, not a
precondition for resolving this item.

## 2. Gather the item's own state

- `title`, `status`, `notes`, `blockers` (free text — this is often the
  most direct statement of what's actually wrong), `track`, `wave`,
  `session` (a link to whatever session previously worked this, if
  recorded — read it as context, not as something to redirect to or wait
  on).
- If `pull_request_number` is set: fetch the PR (`mcp__github__pull_request_read`,
  `method: "get"`) for its mergeable state and CI status
  (`method: "get_check_runs"`), then its review threads
  (`method: "get_review_comments"`) and plain comments
  (`method: "get_comments"`) — read every one, not just the most recent,
  since an older unresolved thread is exactly the kind of thing this skill
  exists to surface. A failing check or a requested-changes review is
  usually the actual blocker; state exactly which one and why, don't just
  say "CI is failing."
- If the item has no PR yet (e.g. blocked before ever starting): there is
  no PR-side state to check — rely on `blockers`/`notes` and the tracking
  issue instead.
- If the plan has a `tracking_issue`, fetch its comments
  (`mcp__github__issue_read`, `method: "get_comments"`) and read every one
  that mentions this item by id, branch, or title — a structural change
  proposed there (a dependency change, a scope split) can be exactly why
  an item stalled.
- `depends_on`: follow `${DEPENDENCY_READINESS_DOCUMENT}`'s bulk-fetch-and-check
  procedure, for `--item <item-id>`. A dependency the script reports not
  ready for (was ready, is now blocked or closed unmerged) is a real,
  common cause of a stall — check this even if `blockers` doesn't mention
  it.
- Read `roadmap.md` **in full** — do not stop at grepping for this item's
  id/branch/title. A roadmap routinely records decisions, conventions, and
  design rationale in sections that don't name every item individually
  (e.g. "Finalized design decisions", "Decisions locked in", a track's own
  design notes, a prior review round's resolution) — those decisions bind
  this item just as much as a direct mention would, and missing one means
  proposing a resolution that contradicts an already-settled call, or
  asking the user something they've already answered. After the full read,
  also grep for the item's id/branch/title specifically, to catch any
  focused mention a full read might skim past. If `roadmap.md` is large
  enough that a full read is genuinely impractical, say so explicitly and
  name which sections you read in full versus grepped — don't silently
  read only part of it and present the plan as if it were comprehensive.

## 3. Read the item's actual existing work

If a branch or PR exists, read what's actually there
(`mcp__github__pull_request_read` for the diff/description,
`mcp__github__get_file_contents` or a local `git fetch` + `git show` for
the real file contents) before proposing anything — the plan must resolve
the real, current state, not a guessed one. For sibling items in the same
track that already landed, read their merged diffs the same way
`plan-item-kickoff` does, when the resolution involves matching an
established pattern (e.g. a review comment asking this item to follow what
a later sibling already settled on).

## 4. Cross-check the standing conventions

Read `roadmap.md`'s standing-conventions section (however it's titled in
this plan) and this repository's own `AGENTS.md`. Whatever the resolution
turns out to be, it must honor both.

## 5. Resolve how this item gets resolved

Follow `${EXECUTION_MODES_DOCUMENT}`: run its `resolve --skill resolve`
call, and if the answer is `ask`, put its question — with a recommendation
drawn from what steps 1-4 just turned up, and the reasons behind it.

Do this only once steps 1-4 are done. What decides the recommendation here
is whether the cause of the stall is actually identified: a named failing
check or review comment with an obvious fix argues for going ahead, and a
blocker whose real cause is still a guess argues for planning first.

Pass `--requested <mode>` when the user named a mode in the invocation
itself.

## 6. Draft the plan

Before drafting the plan or raising any open question with the user, check
whether the question is already answered: re-read the relevant part of
`roadmap.md`, the item's own `notes`/`blockers`, and the PR's/tracking
issue's comment history — a design call, a naming convention, or a scope
boundary is very often already decided somewhere in that material. Only
surface something as an open question if, after that check, it's genuinely
still unresolved; asking the user something the roadmap or the discussion
already answered means the read wasn't thorough enough. If you do ask, say
what you checked and why it still looks open, so the user can correct you
quickly with a pointer if you missed it.

Draft a concrete plan to resolve the item: what's actually wrong (cite the
specific failing check, review comment, blocker text, or regressed
dependency that's the real cause — never a vague "something's blocking
this"), what changes it requires, in which files, in what order, and how
each part will be verified. Cite where each part of the plan came from so it
can be sanity-checked against the source. Flag explicitly, never silently
paper over:

- Any dependency that regressed or still isn't safe to build on.
- Any conflict between what `blockers`/`notes` says and what the PR's own
  review threads or the tracking issue actually say.
- Anything genuinely unresolved after the check above — say so rather
  than filling the gap with an assumption.

In `plan` mode, present it via `ExitPlanMode` and stop there — nothing below
happens until the user approves it, and whether to carry the approved plan
out in this session or a fresh one is their call. In `auto` mode, don't ask:
the plan is settled the moment it is drafted, and the flags above go into
the record described below instead of into a question.

Either way, write no code in this step — its only output is the plan itself.

## 7. Carry it out — `auto` mode only

Work the plan on the item's existing branch, honoring the standing
conventions step 4 cross-checked: tests first per TDD, commits in the user's
own git identity, no assistant author or co-author trailer.

`${EXECUTION_MODES_DOCUMENT}` states what stays owed while doing it, and the
bar for stopping to ask anyway. Two things are this skill's own, because the
item is already underway rather than being started:

- **The record is an update, not a first draft.** Append what the resolution
  turned out to be to `roadmap.md` — especially a blocker whose recorded
  cause turned out to be wrong — and refresh the PR-progress note and the
  pull request description rather than writing them from scratch. Update the
  item's `blockers`, `notes` and `status` where the resolution changed what
  the item means, then republish the dashboard with `/plan-dashboard`.
- **The pull request goes back to draft after the push**, per the user's own
  convention, unless they marked it ready themselves — in which case the
  item was finished and this skill should not have been resolving it.

Finish by reporting what was wrong, what was changed, and what was decided —
in `auto` mode this report is the user's first look at the resolution.
