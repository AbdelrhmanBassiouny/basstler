---
name: plan-dashboard
description: Cross-check a plan's plan.yaml against live GitHub state, correct merged items to done, report drift, and link the plan's page on the plan site. Invoke as "/plan-dashboard <plan-id>". Use when asked to see or refresh a plan's status.
allowed-tools: Bash, Read, Write, AskUserQuestion, Skill
---

# Plan Dashboard

Generic, plan-agnostic tooling — nothing in this file may hardcode a
specific plan's id, branches, or PRs. All plan data lives on the
personal-notes branch (`claude/personal-notes` by default — see
`resolve-personal-notes-config.sh` for how it's resolved) at
`.claude/personal/plans/<plan-id>/plan.yaml` + `roadmap.md`, never on
`main`; this skill only reads it. See `plan-schema.md` (next to this file)
for the full `plan.yaml` schema reference — read it if
anything below is unclear about a field's meaning, rather than guessing.

**Everything deterministic — schema validation, live-state classification,
drift detection, HTML rendering — lives in the committed `basstler` package
(`src/basstler/dashboard/plan_page.py`, `plan/validation.py`,
`pull_request_state.py`, `render_common.py`), not in this document.** This file's job is only
the parts a module can't do: resolving what to fetch and calling the GitHub API.
The plan's page lives on the plan site, which every push to the notes branch
rebuilds; this skill never publishes a page. If you find yourself re-deriving rendering or
validation logic in prose instead of just running the module, stop — that
logic already exists, read it instead of reinventing it.

The whole point of this dashboard is to catch **drift between a plan's
manually-maintained `status` and GitHub's actual live state** (a session
forgot to update a note after a PR shipped, a PR merged without anyone
updating the manifest, a PR number that no longer resolves). Never trust
`plan.yaml`'s `status` field alone — always cross-check live, every run.
One direction of drift (merged on GitHub but not marked `done`) gets
corrected automatically, in the manifest itself, every run — see step 2;
everything else stays a flag for a human to interpret, since GitHub's state
alone can't tell you *why* an item is blocked, deferred, or still open.

## 0. Check the setup is in place, and run it if not

Every step below reads the personal-notes branch and runs scripts that need
the `basstler` package and its dependencies — neither of which a user who
hasn't done the one-time setup has. Follow
`skills/setup-personal-notes/prerequisite-check.md` before step 1: run
the check, and if it reports anything missing, run `/setup-personal-notes`
without asking first, rather than failing later on a missing branch or an
`ImportError`.

## Where the files go

Every file this skill writes goes under `<scratchpad>`: this session's
scratchpad directory, which its system prompt names, or - in a session without
one - a directory under the working directory that git ignores. Never `/tmp`.
Create the directory first (`mkdir -p <scratchpad>/dashboard`).

## 1. Fetch the plan data

The invocation names one `<plan-id>`. Without one, give the plan site's address
(`plan_site_page_url` with no argument) - its repository page lists every plan -
and stop.

Source the shared config script — it resolves the personal-notes
remote/branch precedence (`git config claude.personalNotesRemote` → env var
→ default `origin`; branch likewise defaults to `claude/personal-notes`)
into `NOTES_REMOTE`/`NOTES_BRANCH`, and defines every other script/hook path
this document references below (`REFRESH_DASHBOARD_SCRIPT`, `WRITE_PERSONAL_NOTES_FILE_SCRIPT`,
`BASSTLER_PYTHON`, ...) — read that file if you need the
precise logic or the full list of what it defines. Every bash block in this
document assumes it's already been sourced once per session:

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
fetch_personal_notes_branch
```

Work off `"${PERSONAL_NOTES_REFERENCE}"`, where that fetch keeps the branch — never
`FETCH_HEAD`, which any other fetch overwrites, or `<remote>/<branch>`, which a
URL-form remote never creates.

```bash
git cat-file -e "${PERSONAL_NOTES_REFERENCE}:.claude/personal/plans/<plan-id>/plan.yaml" || {
  echo "No such plan. Available plans:"
  git ls-tree -r --name-only "${PERSONAL_NOTES_REFERENCE}" | grep -E '^\.claude/personal/plans/[^/]+/plan\.yaml$'
  exit 1
}
git show "${PERSONAL_NOTES_REFERENCE}:.claude/personal/plans/<plan-id>/plan.yaml" > <scratchpad>/plan.yaml
git show "${PERSONAL_NOTES_REFERENCE}:.claude/personal/plans/<plan-id>/roadmap.md" > <scratchpad>/roadmap.md  # roadmap.md is always the fixed filename, never configurable
```

Also extract every plan's manifest, into one directory — a `depends_on` entry
may name an item in another plan (`<plan-id>/<item-id>`, see `plan-schema.md`),
and that plan's own manifest is the only thing that can resolve it. This is one
extraction whether the manifest uses the form or not, so do it every run
rather than reading the manifest first to find out:

```bash
mkdir -p <scratchpad>/plans
git archive "${PERSONAL_NOTES_REFERENCE}" "${PLANS_DIR}" \
  | tar -x --strip-components=3 -C <scratchpad>/plans --wildcards '*/plan.yaml'
```

Manifests only, and no roadmaps: the tooling opens a plan's manifest only when
a `depends_on` entry names that plan, and never reads another plan's roadmap at
all. Do not read any of these files yourself — the point of a per-plan size
budget is lost the moment one plan's dashboard run pulls another plan's
contents into the session.

If a plan has a `tracking_issue`, resolve its `html_url` (via
`mcp__github__issue_read` `get`, falling back to
`mcp__github__pull_request_read` `get` if that 404s — a repo with Issues
disabled stores a PR number under the same field, see
`plan-schema.md`'s "Proposing structural changes" section). Use the
returned `html_url` verbatim; don't construct `/issues/<n>` yourself, since
guessing the path is exactly the kind of assumption that breaks silently
when the fallback applies.

## 2. Cross-check every item's PR against live GitHub state, sync, then run the script

Follow `pr-data-fetching.md`'s procedure (next to this file) to assemble
`<scratchpad>/pr_data.json` for every pull request referenced by any item in this
plan, plus any pull request a cross-plan `depends_on` entry names — the
dashboard shows that foreign item's live state too, against its own plan's
repository.

Everything from here on is deterministic - **run `refresh_dashboard.sh`**
rather than reproducing its steps by hand:

```bash
bash "${REFRESH_DASHBOARD_SCRIPT}" \
  --plan-id <plan-id> \
  --plan <scratchpad>/plan.yaml \
  --roadmap <scratchpad>/roadmap.md \
  --pr-data <scratchpad>/pr_data.json \
  --artifact-directory <scratchpad>/dashboard \
  --plans-dir <scratchpad>/plans \
  --tracking-url "<html_url from step 1, if any>"   # omit if the plan has no tracking_issue
```

It runs `plan/sync_manifest_status.py` first - `status` is a manually-maintained
field for everything except one direction: once GitHub confirms a PR is
merged, the item is done, and that's not a judgment call - unlike every
other kind of drift (a bad PR number, "done" while still open, closed
unmerged against an active status), there's no ambiguity to leave for a
human. If that finds anything to correct, it pushes the patched
`plan.yaml` back to the personal-notes branch resolved in step 1 (via
`hooks/write-personal-notes-file.sh`) *before* rendering, so the
dashboard reflects corrected data instead of reporting the same "merged but
not marked done" drift forever; if nothing needed correcting, nothing is
pushed. It then runs `dashboard/plan_page.py`, which validates the manifest
(schema version, unique ids, track/wave/depends_on references — the exact
checks `plan-create` must also satisfy, including a `depends_on` entry naming
another plan, which is resolved against `--plans-dir` and refused if that
plan or item isn't there), classifies every item's live state
(`merged` | `open_draft` | `open_ready` | `closed_unmerged` | `not_found`),
computes drift, builds the "ready to start"/"blocker may be cleared" lists
(a blocked item whose dependency becomes ready always lands in "blocker may
be cleared", never "ready to start" — it's still blocked, not fresh),
stacks items by dependency depth (indented, capped at 4 levels, wrapping
with a left-edge arrow past the cap). `done` items are hidden by default
behind a sidebar toggle ("Show done / merged items") — done client-side via
CSS custom properties, so a dependent item's indentation dedents to
whatever it would be if its done dependencies weren't dependencies at all,
not just one level shallower. Every not-`done` item gets a dashboard action
button, worded to match its status — "Start now" (`plan-item-kickoff`) for
not-started once every dependency is ready, "Resolve"/"Resume"/"Reconsider"
(`plan-item-resolve`) for blocked/in-progress/deferred respectively — plus
a model dropdown beside it; a page can't spawn a session itself, so these
are copy-to-clipboard affordances (the dropdown's choice is prepended as a
`/model <id>` line ahead of the skill command), not live triggers. An item
whose PR is open and still a draft also gets a "Review" button linking
straight to the PR on GitHub — this plan's convention keeps every PR in
draft until its own author has reviewed it, so a draft PR is exactly the
population still needing that review, and flipping it to ready for review
*is* the record of having done so. The sidebar's "Ready to review" list
narrows that population to what's actually worth reviewing right now: not
blocked, not deferred, and every dependency (if any) already has its own
open PR too (the dependency need not itself be past review — just open —
so a whole reviewable stack can surface before its base has merged). Any
sidebar entry whose PR carries the `bug` label is marked with a `bug` chip
where it already sits: a bug fix is a property of the work rather than an
action of its own, so it is never grouped or ordered separately. A "Bug
fixes only" checkbox — shown only when some entry is a bug fix — filters the
sidebar down to them, client-side, with each group's shown count swapped in
alongside its total the same way the done-items toggle swaps indent levels.
Renders the final HTML — including `roadmap.md` converted to HTML and
shown in a collapsed `<details>` section, and the tracking-issue link if
one was passed. None of that is this document's job to describe further;
read the scripts if you need the specifics.

If `refresh_dashboard.sh` exits non-zero, the manifest failed validation —
its stderr says exactly what's wrong (which field, which value). Report
that to the user instead of trying to patch around it yourself; a broken
manifest is something they need to know about, not paper over. Requires
the package's environment, which every session start creates and installs
the package's dependencies into — `hooks/session-start.sh` again if
its `dependencies:` line reported a failure.

On success it prints one merged JSON summary on stdout: `plan/sync_manifest_status.py`'s
own `{"corrected": [...]}` plus `dashboard/plan_page.py`'s status counts, drift
count and drifted/ready/recheck item titles - keep it, you need it for step 3
without re-parsing the HTML it wrote or re-deriving what got auto-corrected.

## 3. Report back

Summarize for the user from the JSON summaries step 2 printed: item counts by
status, every item `plan/sync_manifest_status.py` auto-corrected to done (by
name, since that's a manifest edit the user didn't ask for line by line),
every remaining drift flag by name, and every item now ready to review by
name — this is the actionable output, don't bury it under a wall of
"here's the dashboard" text. End with the plan's page on the plan site:

```bash
plan_site_page_url <plan-id> || echo "No plan site lists this repository yet - /setup-personal-notes publishes one."
```

An auto-correction is a push to the notes branch, so the site rebuilds the page
with it.

## When to refresh

[`manifest-staleness.md`](manifest-staleness.md) says when.

## The plan site

The same pages are also built as one static site that belongs to no account:
the hub at its root, one card per repository; `<owner>/<repo>/` that
repository's plans; `<owner>/<repo>/<plan>/` a plan's dashboard, each linking
back up. Every push to a registered repository's notes branch starts its build. The hub file, `${PLAN_HUB_PATH}` on every registered repository's
notes branch, names the site's address, the registry repository and every
repository listed; the session-start summary's `plan site` line prints where
this session's work sits on it, and `plan_site_page_url [<plan-id> [<item-id>]]`
prints any page's address. To build the site by hand:

```bash
"${BASSTLER_PYTHON}" -m "${BUILD_SITE_MODULE}" --registry <owner/repo> --output <scratchpad>/site
```

Never publish any of these pages as an Artifact: an Artifact belongs to the account
that published it, which is exactly what the site exists to avoid.
