---
name: plan-create
description: Create (or migrate an existing bespoke roadmap doc into) a new multi-PR/multi-session plan under .claude/personal/plans/<plan-id>/plan.yaml on claude/personal-notes, cross-checked against live GitHub, then bootstrap and publish it. Invoke as "/plan-create <plan-id>". Use when the user asks to start tracking something as a plan, set up a new plan/roadmap, or migrate an existing roadmap doc into the plan-dashboard system.
allowed-tools: Bash, Read, Write, Grep, Glob, AskUserQuestion, Skill, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__search_pull_requests
---

# Plan Create

Generic, plan-agnostic tooling — nothing in this file may hardcode a
specific plan's id, branches, or PRs. This is the authoring half of the
plan-dashboard system; `.claude/skills/plan-dashboard/SKILL.md` is the
reading/publishing half. Read `.claude/personal/plans/README.md` (on
`claude/personal-notes`) for the full `plan.yaml` schema before drafting
anything — this skill must produce manifests that pass the exact same
validation `plan-dashboard` step 2 runs, not a close approximation.

The output of this skill is the same as if a session had hand-authored the
manifest via the marker/`save-plan.sh` flow in `save-plan.sh`'s own header
comment — this skill just does that authoring for you, with the same
rigor a careful session would: draft, validate, cross-check live state,
confirm judgment calls with the user, then bootstrap and publish. It never
takes a shortcut a hand-written manifest wouldn't also have to clear.

## 1. Establish the plan id and refuse to silently overwrite

Resolve the personal-notes remote/branch and fetch it (see
`resolve-personal-notes-config.sh`), then check whether
`.claude/personal/plans/<plan-id>/plan.yaml` already exists on `FETCH_HEAD`.
If it does, stop and tell the user — point them at editing the existing
plan (`plan-dashboard`'s doc, or just ask a session to edit it) instead of
silently clobbering it with a fresh draft. Recreating over an existing plan
id is exactly the kind of destructive-by-accident action this system is
meant to prevent, not cause.

If no `<plan-id>` was given, ask for one (kebab-case, short) rather than
inventing one — it's the directory name and the reverse-index key forever.

## 2. Figure out where the plan's content comes from

Ask, don't assume, which of these applies (they can combine — the
`rdr-refactor` reference plan did all three):

- **Migrating an existing freeform doc** (a roadmap markdown file, a
  planning doc on some branch, notes pasted into the conversation). Read it
  in full before drafting anything structured from it — see step 3's
  "preserve, don't summarize-then-lose" rule.
- **Naming existing branches/PRs to track.** Don't take the user's verbal
  description of what state they're in at face value if it's checkable —
  cross-check live per step 4 before it ever goes in the manifest. A plan
  that's stale on day one defeats the entire point of this system.
- **Building from scratch via conversation.** Ask for: title, a one-line
  description, the repo (default to this one unless told otherwise), and
  whether the work has natural waves/phases and parallel tracks, or is
  simple enough to be one track with a flat item list. Don't force a
  wave/track structure onto something that doesn't have one — an
  over-modelled plan is worse than a flat one; see `plans/README.md` on
  why items are flat and tagged rather than nested.

## 3. Draft the structure, surfacing judgment calls rather than guessing

Waves, tracks, item dependency chains, and status assignments are genuine
judgment calls specific to this plan — do not silently invent an answer to
a structural question the source material doesn't settle. Use
`AskUserQuestion` for anything that would be awkward or costly to redo
later (e.g., "is this one track or does it actually split into two once
the work starts stacking?", "should track X's items be sequenced or can
they run in parallel?") — the same way the plan-dashboard system's own
design was worked out via up-front questions before anything was written,
not after.

If migrating a source doc: preserve its detail rather than compressing it
away. Structured facts (branch, PR, base, status, blockers) become
`plan.yaml` items; everything else (design rationale, history, "why",
standing conventions) becomes `roadmap.md`'s narrative — don't drop
content just because it doesn't fit a YAML field. If the source doc has
its own per-branch detail files (this repo's convention:
`.claude/personal/pr-progress/<branch>.md`), you do not need to fold their
full content into `roadmap.md` — that mechanism keeps working independently
of the plan; link to it in spirit (mention it exists) rather than
duplicating it.

## 4. Cross-check every named branch/PR against live GitHub state

Same mechanism as `plan-dashboard` step 3, applied before the item is ever
written down rather than after: bulk-fetch `mcp__github__list_pull_requests`
(`state: "all"`, paginated) for the repo, and use `mcp__github__pull_request_read`
for anything outside that page window or referenced by number in the source
doc. Set each item's `status` from what's actually true (open/draft →
`in_progress` or `not_started` as appropriate, merged → `done`, closed
unmerged → `deferred` with a note), not from what a stale doc or a
half-remembered conversation claims. If the source material and live
GitHub disagree, that disagreement itself is worth a line in the item's
`notes` — it's exactly the kind of drift this system exists to catch, and
noting it once at creation time is cheaper than rediscovering it later.

## 5. Create the tracking PR (coordination mailbox for structural changes)

Ask whether the plan wants one (default yes for anything with more than one
session/track likely to touch it — skip only for something so small a
single session will obviously own it end to end). If yes:

1. Cut a branch off `main` named `plan-tracking-<plan-id>` and make a
   single **empty commit** (`git commit --allow-empty`) — this branch
   carries no file changes, ever; it exists only so GitHub has something to
   open a PR from.
2. Open it as a **draft** PR, base `main`, titled `[plan-tracking]
   <plan-id>`, with a body explaining its purpose (not a code change,
   here's how proposals/replies work — see `plans/README.md`'s "Proposing
   structural changes" section, and `rdr-refactor`'s tracking PR for a
   worked example to copy from). It stays open indefinitely.
3. Subscribe to it (same PR-activity subscription any other PR gets).
4. Record its number as `tracking_pr` in the manifest you're about to write
   in step 6.

This exists because GitHub Issues are disabled on this repo — a PR is the
only native, commentable, subscribable artifact available, not a stylistic
choice. If Issues are ever enabled here, a tracking Issue would be the more
natural fit and this step should switch to that instead.

## 6. Write and validate `plan.yaml` + `roadmap.md`

Follow the schema in `plans/README.md` exactly: `schema_version: 1`, `id`,
`title`, `description`, `default_repo`, `tracking_pr` (if step 5 created
one), `waves[]`, `tracks[]` (each tagged with a `wave`), `items[]` (flat,
each tagged with a `track`, `status` from the thin enum `not_started |
in_progress | blocked | deferred | done`, `depends_on` by item id, optional
`pr`/`session`/`notes`/`blockers`).

Before saving, validate exactly what `plan-dashboard` step 2 validates —
do not diverge from that checklist, since a manifest this skill produces
must pass that same check the first time `/plan-dashboard` runs against it:

- Every `items[].id` (defaulting to `branch` if omitted) is unique.
- Every `items[].track` resolves to a declared `tracks[].id`.
- Every `tracks[].wave` resolves to a declared `waves[].id`.
- Every id in `items[].depends_on` resolves to another `items[].id`.

Parse with Python's `yaml` module to check this mechanically rather than
eyeballing it — the same tooling `save-plan.sh` and `plan-dashboard` both
already require.

## 7. Bootstrap it through the existing write path — don't invent a new one

This skill does not push directly. It uses exactly the flow
`save-plan.sh`'s own header comment documents for a brand-new plan (there
is still no separate create-plan.sh; this skill is what makes that flow
convenient, not a replacement for it):

1. Add the marker pairs to `CLAUDE.local.md` yourself, matching
   `session-start.sh`'s exact format:
   ```
   <!-- BEGIN-PLAN-MANIFEST: <plan-id> -->
   <drafted plan.yaml content>
   <!-- END-PLAN-MANIFEST -->

   <!-- BEGIN-PLAN-ROADMAP: <plan-id> -->
   <drafted roadmap.md content>
   <!-- END-PLAN-ROADMAP -->
   ```
2. Run `.claude/hooks/save-plan.sh <plan-id>` — the id must be explicit
   here, since a brand-new plan has no entry in the reverse index yet for
   `save-plan.sh` to auto-derive it from. This pushes both files to
   `claude/personal-notes` and regenerates the branch→plan-id index in the
   same commit.

## 8. Publish

Invoke the `plan-dashboard` skill for `<plan-id>` to publish its first
dashboard Artifact. Ask the user whether they also want the master index
refreshed (`plan-dashboard` with no argument) — don't do it unprompted,
same convention `plan-dashboard` itself already follows, since that
republishes a second, separate page.

If this was a migration from an existing freeform doc, offer — don't do it
unprompted — to replace that old doc with a short pointer stub at its
original location, the same way the `rdr-roadmap.md` reference migration
did, so anyone still reading the old path finds the new one immediately.

## 9. Report back

Plan id, item/wave/track counts, the dashboard URL, the tracking PR link
if one was created, and — explicitly, not buried — every judgment call you
made or flagged along the way (structural assumptions, any live-vs-source
disagreement found in step 4) so the user can sanity-check them before
relying on the plan.
