---
name: plan-sync
description: Mark every plan item whose pull request merged as done in plan.yaml, push the correction, and link the plan's page on the plan site. Invoke as "/plan-sync <plan-id>". Use when asked to sync or refresh a plan's status.
allowed-tools: Bash, Read, Write, AskUserQuestion, Skill
---

# Plan Sync

Generic, plan-agnostic tooling — nothing in this file may hardcode a specific plan's
id, branches, or PRs. All plan data lives on the personal-notes branch
(`claude/personal-notes` by default — see `resolve-personal-notes-config.sh` for how
it's resolved) at `.claude/personal/plans/<plan-id>/plan.yaml` + `roadmap.md`, never
on `main`. [`plan-schema.md`](../plan-create/plan-schema.md) is the full `plan.yaml`
schema reference — read it if anything below is unclear about a field's meaning,
rather than guessing.

The plan's page on the plan site already shows every item's live GitHub state, its
drift and its next steps; every push to the notes branch rebuilds it. What the site
cannot do is write to the manifest. One direction of drift needs no human judgment:
once GitHub confirms a pull request merged, its item is done. This skill makes that
correction in `plan.yaml` itself, so the page stops reporting it. Every other kind of
drift stays a flag on the page for a person to interpret.

**Everything deterministic lives in the committed `basstler` package
(`plan/sync_manifest_status.py`, `plan/validation.py`, `pull_request_state.py`), not
in this document.** This file's job is only what a module can't do: resolving what to
fetch and calling the GitHub API.

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


## 1. Fetch the plan data

The invocation names one `<plan-id>`. Without one, give the plan site's address
(`plan_site_page_url` with no argument) - its repository page lists every plan -
and stop.

Source the shared config script — it resolves the personal-notes
remote/branch precedence (`git config claude.personalNotesRemote` → env var
→ default `origin`; branch likewise defaults to `claude/personal-notes`)
into `NOTES_REMOTE`/`NOTES_BRANCH`, and defines every other script/hook path
this document references below (`SYNC_PLAN_SCRIPT`, `WRITE_PERSONAL_NOTES_FILE_SCRIPT`,
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

Manifests only: the tooling opens a plan's manifest only when
a `depends_on` entry names that plan, and never reads another plan's roadmap at
all. Do not read any of these files yourself — the point of a per-plan size
budget is lost the moment one plan's sync pulls another plan's contents into
the session.

## 2. Fetch every item's live pull request state, then sync

Follow [`pr-data-fetching.md`](pr-data-fetching.md) to assemble
`<scratchpad>/pr_data.json` for every pull request referenced by any item in this
plan, plus any pull request a cross-plan `depends_on` entry names.

Then **run `sync_plan.sh`** rather than reproducing its steps by hand:

```bash
bash "${SYNC_PLAN_SCRIPT}" \
  --plan-id <plan-id> \
  --plan <scratchpad>/plan.yaml \
  --pr-data <scratchpad>/pr_data.json \
  --plans-dir <scratchpad>/plans
```

It validates the manifest, marks every item whose pull request merged as `done`, and
if that changed anything, pushes the patched `plan.yaml` back to the personal-notes
branch (via `hooks/write-personal-notes-file.sh`); if nothing needed correcting,
nothing is pushed. It prints `{"corrected": [...]}`.

If it exits non-zero, the manifest failed validation — its stderr says exactly what's
wrong (which field, which value). Report that to the user instead of trying to patch
around it yourself.

## 3. Report back

Name every item that was corrected to done — that's a manifest edit the user didn't
ask for line by line — then end with the plan's page on the plan site, where the
remaining drift and next steps are:

```bash
plan_site_page_url <plan-id> || echo "No plan site lists this repository yet - /setup-personal-notes publishes one."
```

## When to sync

[`manifest-staleness.md`](manifest-staleness.md) says when.

## The plan site

The hub at the site's root has one card per repository; `<owner>/<repo>/` lists that
repository's plans; `<owner>/<repo>/<plan>/` is a plan's page, each linking back up.
Every push to a registered repository's notes branch starts its build. The hub file,
`${PLAN_HUB_PATH}` on every registered repository's notes branch, names the site's
address, the registry repository and every repository listed; the session-start
summary's `plan site` line prints where this session's work sits on it, and
`plan_site_page_url [<plan-id> [<item-id>]]` prints any page's address. To build the
site by hand:

```bash
"${BASSTLER_PYTHON}" -m "${BUILD_SITE_MODULE}" --registry <owner/repo> --output <scratchpad>/site
```

Never publish any of these pages as an Artifact: an Artifact belongs to the account
that published it, which is exactly what the site exists to avoid.
