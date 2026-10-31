# `plan.yaml` schema reference

The full field-by-field reference for a plan manifest: a generalized
replacement for one-off master-roadmap docs when tracking a
multi-PR/multi-session initiative. A structured `plan.yaml` drives
generation; a sibling `roadmap.md` carries the plan's standing rules. Both
hold only what a future session needs to act - see "Size limits" below.

This document lives on `main`, alongside the tooling that reads it — it is
generic, plan-agnostic reference material, so every clone has it with no
setup. The **plan data it describes** is the opposite: it is never merged
into `main`, living only on the personal-notes branch (`claude/personal-notes`
by default — see [`resolve-personal-notes-config.sh`](../../hooks/resolve-personal-notes-config.sh)
for how that's resolved), exactly like the personal notes and `pr-progress/*.md`.

New to the system and want to see it end to end before reading the schema?
Start with [`example-walkthrough.md`](./example-walkthrough.md), a short
worked example from a plan-mode idea to a published dashboard. A complete,
schema-conformant manifest you can read alongside this reference is
committed at [`example/plan.yaml`](./example/plan.yaml), with its standing
rules at [`example/roadmap.md`](./example/roadmap.md).

## Layout

```
.claude/personal/plans/
  _generated/
    branch-index.tsv          (generated - do not hand-edit, see below)
  _hub.yaml                   (the plan site's hub file - see basstler.plan_site.hub)
  <plan-id>/
    plan.yaml
    roadmap.md
```

`<plan-id>` is a short kebab-case slug — it's the directory name, the `id`
field inside `plan.yaml`, and the key the generated reverse index uses.
Entries that are not plans start with `_`, which a kebab-case slug never does, so they
can never collide with a plan's directory.

## `plan.yaml` schema (schema_version: 1)

```yaml
schema_version: 1
id: <plan-id>                  # matches the directory name
title: "Human-readable title"
description: >
  One short paragraph.
default_repository: <owner>/<repo>   # used by every item unless it sets its own `repository`
                                       # (roadmap.md is a fixed sibling filename, not configurable)
tracking_issue: <int, optional> # see "Proposing structural changes" below

waves:                         # ordered phases, purely organizational
  - id: <wave-id>
    name: "Human-readable name"
    description: "optional"

tracks:                        # a parallel line of work within a wave
  - id: <track-id>
    name: "Human-readable name"
    wave: <wave-id>
    description: "optional"

items:                         # the actual trackable units of work - flat,
                                # not nested under wave/track, so any item can
                                # depend_on any other regardless of nesting
  - id: <item-id>               # defaults to `branch` if omitted; must be
                                 # unique. Prefer the real branch name unless
                                 # it's an auto-generated session slug, in
                                 # which case a readable id is worth the
                                 # divergence.
    title: "What this item does"
    branch: <branch-name>       # the actual git branch, once one exists
    repository: null            # optional, overrides default_repository
    pull_request_number: <int or null>  # the real GitHub PR number, once one exists
    track: <track-id>
    depends_on: [<item-id>, ...]  # structural/stacking dependency - a bare id for
                                   # an item of this plan, <plan-id>/<item-id> for
                                   # one in another plan (see below)
    status: not started | in progress | blocked | deferred | done  # underscores (not_started) still read
    session: <url or omitted>
    notes: "short, freeform"
    blockers: ["freeform reasons", ...]   # optional, defaults to []
```

Validation is not documentation-only: `plan/validation.py` enforces this
schema on every `/plan-dashboard` run, and `/plan-create` drafts against the
same checks. If this document and that module ever disagree, the module is
the authority.

### Why `status` is deliberately thin

`status` is only ever the session's own manual planning assessment. It
never encodes draft/ready-for-review/merged/closed/CI-green/mergeable —
those are fetched live from GitHub every time `/plan-dashboard` runs, so
they can never go stale in the manifest. The dashboard shows both side by
side and flags any item where the two disagree (e.g. `status: in progress`
on a PR that's already merged) — this is the actual mechanism that replaces
"a session has to notice a note is stale by accident."

**One exception, corrected automatically.** Most drift needs a person to
interpret it — GitHub's state alone can't say whether a still-open PR means
"blocked", "deferred", or just "in progress", and a mismatched PR number
usually means the manifest was mistyped, not that GitHub is wrong. But
"GitHub confirms this PR is merged" has exactly one correct manifest state:
`done`. There's nothing to interpret, so `/plan-dashboard` doesn't just flag
it — `plan/sync_manifest_status.py` corrects `status` to `done` for exactly that
case, in `plan.yaml` itself, every run, before rendering. Every other kind
of drift is still left as a flag for a human.

### Depending on an item in another plan

A `depends_on` entry is a bare `<item-id>` when it names an item of the same
plan, and `<plan-id>/<item-id>` when it names one in another plan. Neither
kebab-case id can contain a `/`, so the two forms never collide, and a plan
that depends on nothing outside itself never has to know the form exists.

A precondition that lives in another plan used to have nowhere to go but a
freeform `blockers` sentence, which nothing resolves, re-checks or renders. A
reference is checked and shown like any other dependency: `/plan-dashboard`
resolves it against the referenced plan's own manifest, renders it as a chip
that opens that item's card on its plan's page of the plan site in a new tab,
and reads the foreign item's live pull request state from its own plan's
`default_repository`. A chip naming an item of this plan scrolls to that item's
card on the same page.

Four rules, each rejected outright rather than passed over:

- The plan must be in the plans directory, and the item must be in that plan.
  An unknown plan or item is refused with the same shape of error an unknown
  same-plan id already gets.
- A reference must not name **this** plan's own id — the bare id already names
  that item, and one edge should not have two spellings.
- A reference has exactly two halves. A third segment would have to mean a
  plan inside a plan, which means nothing.
- A cross-plan reference needs the plans directory to resolve against, so a
  manifest carrying one is refused when the tooling was given no directory
  (`--plans-dir`, see [`SKILL.md`](./SKILL.md)). Accepting it unchecked is how
  an unresolvable dependency used to count as *ready*.

The cycle check runs over the resulting union graph, so a loop that closes
through another plan is caught even though neither manifest can see it alone.
Indentation is unaffected: an item's indent level is its depth in the
**same-plan** dependency chain, since an item in another plan has no card on
this page to indent under.

Only the plans some entry actually names are read, and only their manifests —
never their roadmaps, and never a plan nothing here depends on. What reaches
the page from a foreign plan is one chip per reference: the reference text, the
foreign item's title, its plan's title, and its live state. Keeping one plan's
dashboard from carrying another plan's contents is the whole point of a
per-plan size budget.

### Why items are flat, not nested under wave/track

A track can span or reprioritize across waves, and `depends_on` needs to
reference any other item directly by id. Nesting would either duplicate
items across waves or force awkward cross-links. Tag each item with the
`track` it belongs to instead; look up that track's `wave` for grouping in
the dashboard.

## The generated reverse index

`.claude/personal/plans/_generated/branch-index.tsv` maps every item's
`branch` (across every plan) to that plan's `id`. It is regenerated by
[`save-plan.sh`](../../hooks/save-plan.sh) in the same commit as any
`plan.yaml`/`roadmap.md` push, by scanning every `plans/*/plan.yaml` — never
hand-maintained, so it cannot drift out of sync with the manifests it's
derived from.

`session-start.sh` reads it to auto-load the parent plan's `plan.yaml` +
`roadmap.md` into `CLAUDE.local.md` whenever the checked-out branch appears
in some plan's `items[]`, exactly like the existing per-branch PR-progress
lookup already does for `pr-progress/<branch>.md`.

## Creating a new plan

[`plan-create/SKILL.md`](../plan-create/SKILL.md) (`/plan-create <plan-id>`)
automates this: it gathers the plan's scope (an existing freeform roadmap doc
to migrate, named branches/PRs to cross-check live, or plain conversation),
drafts a schema-conformant `plan.yaml`/`roadmap.md`, validates it against the
same checks `plan-dashboard` runs, asks before assuming anything that's a real
structural judgment call, then runs `save-plan.sh` and `/plan-dashboard`
itself.

## Size limits

Every session that loads a plan pays for every line of it, so the plan holds
only what a future session needs to act. `save-plan.sh` enforces this with
the limits `src/basstler/plan/size_limits.py` names (`Measure`):

- **Landed items are dropped on save**, along with every `depends_on` edge to
  them: the work is in the code and its history in git. A plan left with no
  items is removed.
- **Fields are bounded**: items per plan, characters of the description,
  characters of each item's `notes`, blockers per item and characters of each.
  `notes` hold the item's scope and the decisions that bind it, not a log of
  sessions; a blocker names what is awaited and from whom, in a sentence.
- **`roadmap.md` is a list of standing rules**: a `# ` title, then `- `
  entries (continuation lines indented two spaces), bounded in count and
  length. Any other line - a dated section, a paragraph, a heading - is
  refused.
- **PR progress notes** are bounded too, enforced by `save-pr-progress.sh`:
  the plan, what is done, and what is next.

A save over a limit is refused with every violation named. Read one item
rather than the manifest with
`"${BASSTLER_PYTHON}" -m basstler.plan.manifest_tools item <file> --id <item-id>`.

## Editing an existing plan

Fetch the personal-notes branch, note the commit you read
(`git rev-parse "${PERSONAL_NOTES_REFERENCE}"`), copy `plans/<plan-id>/plan.yaml` and
`roadmap.md` to scratch files, edit them, then run

```bash
"${BASSTLER_PLUGIN_ROOT}/hooks/save-plan.sh" <plan-id> --manifest <file> --roadmap <file> \
  --read-at <commit>
```

to push both files and regenerate the reverse index in one commit. The save
applies each top-level field, item and roadmap you changed since `<commit>`
onto the branch as it is now, so another session's edit to a different item
survives; it refuses (exit 3) when someone else changed the same part, and
retries a push the branch rejected. Without `--read-at`, your files overwrite
whatever changed before the save first fetches. This
pushes data only — it does not publish the dashboard Artifact itself (that
requires a live Claude session, since only a session can call the
`Artifact` tool). `save-plan.sh` prints a reminder to run
`/plan-dashboard <plan-id>` afterward to actually republish it.

## Proposing structural changes (broadcast via a tracking issue)

Editing `status`, `notes`, or `blockers` on an item you're actively working is
a normal edit — do it directly, as above. **Structural** changes (adding a
wave, deferring a track, splitting an item, reprioritizing) are different:
they're judgment calls about the whole plan, not just the one item a session
happens to be sitting on — but there is no designated steward gatekeeping
them. Any session can make one directly, but only after asking the user in the
session itself (e.g. via `AskUserQuestion`) — a structural change is the
user's call, not something to infer and apply unilaterally just because
editing the manifest directly is technically allowed.

Once confirmed, if a plan has a `tracking_issue` (its number, in the
repository named by `default_repository`), the session **also comments on that
issue describing the change**, in addition to editing `plan.yaml` directly —
it's a coordination mailbox, not a work item, and is subscribable exactly like
a PR (GitHub issue-comment subscription works identically whether the number
is an issue or a PR). This is not a proposal awaiting approval from a
gatekeeping session: the user reviews structural changes there themselves, and
the comment is the shared record every other session working the plan can
check. `/plan-create` creates the tracking issue (titled
`[plan-tracking] <plan-id>`) when bootstrapping a new plan and records its
number as `tracking_issue` in `plan.yaml`.

**Staying aware while working an item.** A session working an item in a plan
that has a `tracking_issue` reads that issue's comments when it starts and
again before each push - not just the session making a structural change -
since every structural change is posted there. No tool delivers an issue's
comments as they arrive: the pull-request activity subscription refuses an
issue. Only a tracking pull request (the fallback below) can be subscribed to.
`session-start.sh`'s written header reminds a session of this when it
auto-discovers the plan.

**Fallback when a repo has Issues disabled**: some repos disable Issues
entirely — GitHub returns a `410` on creation attempts. When that happens,
`/plan-create` falls back to an empty-commit, permanently-draft **tracking
PR** instead (same subscribable-mailbox mechanism, just a PR instead of an
issue) and still records its number under the same `tracking_issue` field —
the field name describes the *role* (a tracking mailbox), not literally "must
be a GitHub Issue object." Whoever reads it should check which kind it
actually is (an issue-vs-PR read call distinguishes them) before building a
link, rather than assuming.

If a plan has no `tracking_issue` set, there's no mailbox yet — structural
edits go straight to `plan.yaml` as before (single-session plans, or ones
predating this convention, don't need one).

## Generating a dashboard

See [`plan-dashboard/SKILL.md`](./SKILL.md). Invoke it as
`/plan-dashboard <plan-id>` for one plan's dashboard, or `/plan-dashboard`
with no argument for the master index listing every plan found on the
personal-notes branch.
