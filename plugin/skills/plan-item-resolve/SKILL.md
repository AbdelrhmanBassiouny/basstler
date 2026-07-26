---
name: plan-item-resolve
description: Gather everything available about one already-underway tracked plan item (its plan.yaml entry, roadmap.md history, the real state of its branch/PR - conflicts, CI, review comments - and any relevant discussion on its plan's tracking issue) and propose a concrete plan to resolve whatever is stalling it, via plan mode, without writing any code. Invoke as "/plan-item-resolve <plan-id> <item-id>". Use when resolving a blocked, in-progress, or deferred item from a plan-dashboard's "Resolve"/"Resume"/"Reconsider" link, or when the user asks to "resolve", "unblock", "resume", or "reconsider" a specific tracked item.
allowed-tools: Bash, Read, Grep, Glob, Skill, EnterPlanMode, ExitPlanMode, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__issue_read, mcp__github__get_file_contents, mcp__github__search_code
---

# Plan Item Resolve

Generic, plan-agnostic — nothing here may hardcode a specific plan id,
item, or branch. Unlike `plan-item-kickoff` (for an item that hasn't
started), this skill is for an item that already has real state - a
branch, a PR, prior review, a recorded blocker - and needs that state
understood before proposing what to do next. **This skill never writes
code, creates a branch, or pushes anything** — it is a research-and-planning
skill, not an implementation one. Every invocation starts fresh in the
current session; it does not try to detect or resume any other session.

## 1. Resolve the item

Fetch the personal-notes branch and load `<plan-id>/plan.yaml` +
`roadmap.md` (same resolution `.claude/skills/plan-dashboard/SKILL.md` step
1 uses — read that file if the precedence is unclear rather than
re-deriving it). Find the item by `id` (or `branch` if `id` is unset) among
`items[]`.

If the plan id or item id doesn't resolve, stop and list what's actually
available (every plan id under `plans/*/plan.yaml`, or every item id in the
named plan) rather than guessing which one was meant.

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
- `depends_on`: resolve each id to its own item and cross-check its live
  GitHub state the same way `build_dashboard.py` does (bulk-fetch every
  referenced PR via `mcp__github__list_pull_requests`, falling back to
  `mcp__github__pull_request_read` for anything outside that page window).
  A dependency that regressed (was ready, is now blocked or closed
  unmerged) is a real, common cause of a stall — check this even if
  `blockers` doesn't mention it.
- Every place `roadmap.md` mentions this item by id, branch, or title —
  design rationale and prior decisions usually live there, not in
  `plan.yaml`'s thin structured fields.

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

## 5. Propose the plan — plan mode, no code

Enter plan mode and present, via `ExitPlanMode`, a concrete plan to
resolve the item: what's actually wrong (cite the specific failing check,
review comment, blocker text, or regressed dependency that's the real
cause — never a vague "something's blocking this"), what changes it
requires, in which files, in what order, and how each part will be
verified. Cite where each part of the plan came from so the user can
sanity-check it against the source. Flag explicitly, never silently paper
over:

- Any dependency that regressed or still isn't safe to build on.
- Any conflict between what `blockers`/`notes` says and what the PR's own
  review threads or the tracking issue actually say.
- Anything genuinely unresolved after gathering all of the above — say so
  rather than filling the gap with an assumption.

Do not touch git, create a branch, or write any code in this skill — its
only output is the plan itself.
