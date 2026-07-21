---
name: plan-dashboard
description: Publish a live status dashboard Artifact for a multi-PR/multi-session initiative tracked under .claude/personal/plans/<plan-id>/plan.yaml on claude/personal-notes, cross-checked against live GitHub PR/CI/review state. Invoke as "/plan-dashboard <plan-id>" for one plan, or "/plan-dashboard" with no argument to publish the master index of every plan. Use when the user asks to see, refresh, or generate a plan dashboard, or asks "what's the status of <plan>".
allowed-tools: Bash, Read, Write, Grep, Glob, Artifact, Skill
---

# Plan Dashboard

Generic, plan-agnostic tooling — nothing in this file may hardcode a
specific plan's id, branches, or PRs. All plan data lives on
`claude/personal-notes` (`.claude/personal/plans/<plan-id>/plan.yaml` +
`roadmap.md`), never on `main`; this skill only reads it. See
`.claude/personal/plans/README.md` (on `claude/personal-notes`) for the full
`plan.yaml` schema reference — read it if anything below is unclear about a
field's meaning, rather than guessing.

The whole point of this dashboard is to catch **drift between a plan's
manually-maintained `status` and GitHub's actual live state** (a session
forgot to update a note after a PR shipped, a PR merged without anyone
updating the manifest, a PR number that no longer resolves). Never trust
`plan.yaml`'s `status` field alone — always cross-check live, every run.

## 1. Resolve mode and fetch the plan data

Determine mode from the invocation argument: a `<plan-id>` argument means
single-plan mode; no argument means master-index mode.

Resolve the personal-notes remote/branch with the exact same precedence
`.claude/hooks/resolve-personal-notes-config.sh` uses (read that file if you
need the precise logic): `git config claude.personalNotesRemote` → env var
→ default `origin`; branch likewise defaults to `claude/personal-notes`.
Then:

```bash
git fetch "${NOTES_REMOTE:-origin}" "${NOTES_BRANCH:-claude/personal-notes}" --quiet
```

Work off `FETCH_HEAD`, not `<remote>/<branch>` — a URL-form remote creates
no tracking ref (same reasoning as every hook script here).

**Single-plan mode:**

```bash
git cat-file -e "FETCH_HEAD:.claude/personal/plans/<plan-id>/plan.yaml" || {
  echo "No such plan. Available plans:"
  git ls-tree -r --name-only FETCH_HEAD | grep -E '^\.claude/personal/plans/[^/]+/plan\.yaml$'
  exit 1
}
git show "FETCH_HEAD:.claude/personal/plans/<plan-id>/plan.yaml" > /tmp/plan.yaml
git show "FETCH_HEAD:.claude/personal/plans/<plan-id>/roadmap.md" > /tmp/roadmap.md  # roadmap.md is always the fixed filename, never configurable
```

**Master-index mode:** enumerate every plan instead of one:

```bash
git ls-tree -r --name-only FETCH_HEAD | grep -E '^\.claude/personal/plans/[^/]+/plan\.yaml$'
```

Load each one the same way as above, into `/tmp/plans/<plan-id>/plan.yaml`.

Also read the generated URL cache, if present (used in step 5, absent on a
plan's first-ever publish — not an error):

```bash
git show "FETCH_HEAD:.claude/personal/plans/_generated/dashboard-urls.yaml" 2>/dev/null
```

## 2. Parse and validate

Parse with Python's `yaml` module (`python3 -c "import yaml, json; ..."` or
a short scratch script) rather than hand-rolling a YAML reader. For each
plan loaded, validate:

- `schema_version == 1`.
- Every `items[].id` is unique (default an item's `id` to its `branch` if
  the field is omitted — see the schema doc for why the two can differ,
  e.g. a session's auto-generated branch slug vs. the plan's conceptual
  name).
- Every `items[].track` resolves to a declared `tracks[].id`.
- Every `tracks[].wave` resolves to a declared `waves[].id`.
- Every id in `items[].depends_on` resolves to another `items[].id`.

If validation fails for a plan, report exactly what's wrong (file, field,
value) instead of silently skipping it — a broken manifest is itself
something the user needs to know about, not something to paper over.

## 3. Cross-check every item against live GitHub state

For each distinct repo referenced (`items[].repo` if set, else the plan's
`default_repo`), fetch PR state **once, in bulk**, rather than one API call
per item — with ~30+ items per plan this matters:

1. `mcp__github__list_pull_requests` with `state: "all"`, `perPage: 100`,
   paginating (`page`) until a page comes back short of 100. Build a
   `{number: {state, draft, merged_at, base_ref, head_ref, html_url}}`
   lookup from the results.
2. For any item whose `pr` isn't in that lookup (older than the pagination
   window covered), fall back to `mcp__github__pull_request_read` with
   `method: "get"` for that specific `pullNumber`. If it 404s, record that
   explicitly (`live_state: not_found`) — do not treat a lookup failure as
   "must be fine."

Classify each item with a `pr` set into one live state:
`merged` | `open_draft` | `open_ready` | `closed_unmerged` | `not_found`.
Items with `pr: null` have no live state to check — that's expected for
`not_started`/`blocked`/`deferred` items with no branch cut yet, not a gap
to flag.

**Drift rules** (flag every one you find, don't silently correct them):

- `status: done` but live state is `open_draft`/`open_ready` → stale
  "done", the PR isn't actually merged.
- `status` in `not_started`/`blocked`/`deferred` but live state is `merged`
  → the work shipped and nobody updated the manifest (this happened for
  real in `rdr-refactor`'s `rdr-why-answer` item — see its `notes` field).
- `status: in_progress`/`blocked` but live state is `merged` or
  `closed_unmerged` → manifest is behind reality either way.
- live state is `not_found` for any item with a `pr` set → the PR number
  is wrong or the PR was deleted; surface this loudly, don't guess a fix.

## 4. Build the dashboard

**Before writing any HTML, load the `artifact-design` skill** to calibrate
the design for this content (a status dashboard, not a data chart — if it
ends up needing real charts/sparklines, load `dataviz` too).

**Single-plan mode**, structure the page by wave → track → items:

- Header: plan title, description, a link to `roadmap.md`'s content isn't
  publishable as a link (it's not on GitHub) — instead render its content
  inline in a collapsible "background/history" section, or summarize it
  and note full detail lives in `roadmap.md`.
- Per item: title, id, branch, a real `https://github.com/<repo>/pull/<n>`
  link when `pr` is set (never fabricate a link when `pr` is null — just
  show "no PR yet"), the manual `status`, the live GitHub state, session
  link if present, notes, blockers. Visually distinguish any item flagged
  in step 3 as drifted — that's the single most important signal this
  dashboard exists to surface, it should not read as just another badge.

### Stack items within a track by dependency depth (indent, cap at 4, wrap with an arrow)

Within each track, items form a dependency chain/tree via `depends_on`
(restricted to same-track ids — a `depends_on` pointing at another track is
still shown as a small chip reference, it just doesn't drive indentation,
since the two items aren't rendered near each other). Render each track as
an indented stack rather than a flat list:

1. Roots = items with no same-track `depends_on`. Root indent level = 0.
2. A child's indent level = its (same-track) parent's level + 1.
3. **Cap at level 4.** If a child's computed level would exceed 4, reset it
   to level 0 instead of indenting further, and mark it as a "wrapped"
   item.
4. Render a wrapped item with a small left-edge arrow/connector (e.g. "◄
   continues from `<parent id>`") pointing at its actual parent, since it's
   no longer visually nested under it. Do not attempt to draw an absolutely-
   positioned line/SVG connector between two arbitrary DOM nodes — that's
   fragile in a static artifact with reflowing content; a legible inline
   arrow chip naming the parent is the robust version of "an arrow from the
   left of the child to its parent."
5. A long linear stack (a straight PR chain, the common case for a
   steward-style track) will wrap repeatedly — level 0,1,2,3,4, then back to
   0,1,2,3,4, etc. This is expected, not a bug.

### Summary sidebar: statuses + what to do next

Give the page a sticky summary sidebar (collapses to a stacked section
above the content on narrow viewports) containing:

- **Status counts** (done/in_progress/blocked/deferred/not_started) and the
  drift count from step 3.
- **What to do next** — computed, not hand-authored, in this priority order:
  1. Every drifted item from step 3 (fix the manifest — highest priority,
     it means the plan doesn't reflect reality).
  2. **Ready to start**: items with `status` `not_started` or `blocked`
     whose *every* `depends_on` item has live/manual status `done` — these
     have nothing left blocking them structurally.
  3. **Blocker possibly cleared**: `blocked` items where at least one
     `depends_on` item is `done` but not all of them are — worth a manual
     check of whether the blocker text is still accurate.
  Keep this list short and concrete (item title + one-line reason) — it's
  the "what do I do when I open this dashboard" answer, not a restatement
  of the full item list already below it.

**Master-index mode**, one row per plan: title, description, `done`/total
item count, and a link to that plan's own dashboard (its `dashboard_url`
from the URL cache read in step 1 — if a plan has never been published yet,
say so plainly rather than linking nowhere). Show completed plans (100% of
items `done`) in a visually de-emphasized/collapsed way rather than hiding
them — every plan that exists should be discoverable from the index.

Favicon: keep a single stable emoji across every redeploy of the **same**
artifact identity. Suggested: 📋 for a per-plan dashboard, 🗂️ for the master
index — pick your own if these clash with something already published, but
keep whichever you pick fixed for that artifact going forward.

## 5. Publish, and keep the URL cache in sync

Look up this plan's (or, in index mode, the index's own — use the fixed key
`_index`) existing URL from the `dashboard-urls.yaml` you read in step 1.
Call `Artifact` with that as `url:` if found (updates the existing page in
place); omit `url` if this is a first-ever publish (mints a new one).

If this was a first publish, or the returned URL differs from the cache,
update the cache and push it back — a small scratch-worktree commit,
matching every other write in this system (see
`.claude/hooks/save-personal-notes.sh` for the exact pattern: fetch, worktree
add on `FETCH_HEAD`, write the file, commit, push, clean up the worktree and
temp branch). Do not touch the user's current branch or working tree to do
this.

```bash
# sketch — adapt paths/remote/branch to what step 1 resolved
SCRATCH="$(mktemp -d)"
git worktree add -b __plan-dashboard-tmp "$SCRATCH" FETCH_HEAD --quiet
mkdir -p "$SCRATCH/.claude/personal/plans/_generated"
# merge your updated url(s) into the existing dashboard-urls.yaml content, then:
cp /tmp/updated-dashboard-urls.yaml "$SCRATCH/.claude/personal/plans/_generated/dashboard-urls.yaml"
git -C "$SCRATCH" add .claude/personal/plans/_generated/dashboard-urls.yaml
git -C "$SCRATCH" commit --quiet -m "Record dashboard URL for <plan-id or _index>"
git -C "$SCRATCH" push "${ACTIVE_NOTES_REMOTE}" "HEAD:${NOTES_BRANCH}"
git worktree remove --force "$SCRATCH"
git branch -D __plan-dashboard-tmp
```

Skip this whole step if the URL you already had matches what `Artifact`
returned — nothing changed, nothing to push (same "safe to re-run,
no-op-if-unchanged" convention as the other scripts here).

## 6. Report back

Summarize for the user: item counts by status, and call out every drift
flag from step 3 by name — this is the actionable output, don't bury it
under a wall of "here's the dashboard" text. Give the Artifact link(s).

If you're in single-plan mode and the master index already exists (its URL
is in the cache), mention that it wasn't refreshed automatically and the
user can run `/plan-dashboard` with no argument to update it too — don't do
it unprompted, since that republishes a second, separate page.

## Refreshing after a manifest edit

This skill is the second half of the refresh loop
`.claude/hooks/save-plan.sh` starts: that script pushes an edited
`plan.yaml`/`roadmap.md` and regenerates the branch reverse index, but it
cannot call the `Artifact` tool itself (only a live Claude session can) — it
prints a reminder to run `/plan-dashboard <plan-id>` afterward, which is
this skill.
