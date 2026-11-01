---
name: add-plan-item
description: Decide where new work belongs - folded into an unlanded item, a new item, a new plan, or untracked - and propose it via plan mode without writing code. Invoke as "/add-plan-item <description of the work>". Use when asked where new work goes, to add a plan item, or whether it should be its own PR.
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion, Skill, EnterPlanMode, ExitPlanMode, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__get_file_contents, mcp__github__issue_read, mcp__claude-code-remote__subscribe_pr_activity
---

# Add Plan Item

Generic, plan-agnostic — nothing here may hardcode a specific plan id, item,
or branch. Takes a description of something to build and decides where it
belongs, before any branch exists to regret. **This skill never writes code,
creates a branch, or pushes anything** — its only output is a proposed plan.

There are exactly four outcomes, and step 6 picks one:

1. **Fold** it into an unlanded item or branch that already owns this work.
2. **New item** in a plan that already exists.
3. **New plan** of its own, via `/plan-create`.
4. **No item at all** — work small enough that tracking it costs more than it
   returns.

## 0. Check the setup is in place, and run it if not

Every plan's manifest lives on the personal-notes branch, which the user may not
have set up yet. Follow
`skills/setup-personal-notes/prerequisite-check.md` before step 1: run
the check, and if it reports anything missing, run `/setup-personal-notes`
without asking first, rather than failing on a branch that isn't there.

## 1. Pin down what the work actually touches

The check in step 3 needs two things the description rarely states outright:

- **The paths** the work would create or modify.
- **The base branch** it ultimately targets (usually the repository's default
  branch, but a plan may target something else).

Derive the paths by reading the repository — find where comparable work already
lives and name the files this would add or change. Only if they are still
genuinely underdetermined after that, ask via `AskUserQuestion`. Never skip
step 3 for want of paths: an unrun check is exactly how work ends up on its own
branch by default.

## 2. Find the candidate homes

```bash
source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
fetch_personal_notes_branch
```

Read **every** plan's `plan.yaml` under `${PLANS_DIR}` off `"${PERSONAL_NOTES_REFERENCE}"`, not
just the one the user has in mind — the right home is often a plan they weren't
thinking of. [`plan-schema.md`](../plan-dashboard/plan-schema.md) is the field reference.

Then fetch live pull request state once, in bulk, per
[`pr-data-fetching.md`](../plan-dashboard/pr-data-fetching.md).

Candidates are every unlanded item and every open pull request's branch, plus
every plan whose own `description` covers the kind of work being described.

## 3. Run the scope check

The rule is in [`scope-decision.md`](scope-decision.md) — read it rather than re-deriving
it here. Gather its evidence in one call:

```bash
"${BASSTLER_PYTHON}" -m "${CHECK_SCOPE_OVERLAP_MODULE}" \
    --base <base-branch> \
    --path <path> [--path <path> ...] \
    --candidate '<item-id-or-title>=<branch>' [--candidate ... ]
```

Non-empty `paths_absent_from_base` means an unlanded branch introduces those
files, and whichever one does is a candidate owner. Non-empty `shared_paths`
names it. Apply the trigger-to-look test from [`scope-decision.md`](scope-decision.md) to
decide what that means; do not treat the output as the verdict by itself.

## 4. Scan for duplicate intent

Two branches building the same thing under different filenames share no path,
so the script cannot flag them. Read each candidate's `changed_paths` and
compare what those branches are *for* against what is being described. A
match here outranks the path check: same purpose is the same work, whatever
the files are called.

## 5. Check whether a covering plan still has room

A plan's `description` covering the work is not enough by itself — it also has
to have room left. For every plan found in step 2 whose `description` covers
the work, count its *current* items (manifest already fetched off
`FETCH_HEAD`) against the item limit, `Measure.ITEM_COUNT` in
`plan/size_limits.py`:

```bash
git show FETCH_HEAD:"${PLANS_DIR}/<plan-id>/plan.yaml" > <scratchpad>/plan.yaml
"${BASSTLER_PYTHON}" -m "${PLAN_SIZE_CHECK_MODULE}" --manifest <scratchpad>/plan.yaml
```

`is_full: true` disqualifies that plan for growth, whatever its `description`
says — the plan is already at `item_limit`, so `save-plan.sh` would refuse it
one more item, and proposing it here only moves that refusal to whoever next
saves the plan. Landed items are not counted, since a save prunes them first.

Check every covering plan this way before ruling out **New item in an
existing plan** entirely — a plan qualifies only if it fits both ways, topic
*and* room; a full plan is disqualified even if its `description` fits, and a
plan with room is never a candidate if its `description` doesn't cover the
work in the first place. Only when no plan satisfies both does the outcome
fall through to **New plan**.

## 6. Choose exactly one outcome

- **Fold** — the work has nothing substantial left once the overlapping edits
  are removed, or a candidate is already building the same thing. Name the
  branch it goes on.
- **New item in an existing plan** — it stands on its own, a plan's
  `description` covers it, and step 5 found that plan not full. Name the plan,
  the track, the wave, and any real `depends_on`.
- **New plan** — it stands on its own, spans several pull requests or
  sessions, and either no existing plan covers it or every plan that does is
  already full (step 5). Hand off to `/plan-create` via the `Skill` tool
  rather than drafting a manifest here — if the reason is a full plan rather
  than no coverage at all, say so, citing the item count step 5 found. A full
  plan that could itself be split is a second way out: put both options to
  the user with `AskUserQuestion`, with your recommendation, instead of
  choosing for them.
- **No item at all** — one self-contained change, done in this session, that
  nothing else depends on. `plan-create`'s own guidance against over-modelling
  applies: a plan that tracks everything is a plan nobody reads.

If two outcomes remain genuinely open after steps 3 and 4, put the choice to
the user with `AskUserQuestion`, giving the evidence for each rather than
asking them to re-derive it.

## 7. Propose the plan — plan mode, no code

Enter plan mode and present, via `ExitPlanMode`, the chosen outcome and what
follows from it. Cite where each part came from — the script's output, a
specific plan's `description`, a candidate branch's diff — so the user can
check it against the source instead of just trusting it.

**If the outcome is a fold**, the proposal must say which branch the work goes
on *and* what happens to any branch already opened for it — reset onto the
parent, or move the commits over and retire the redundant branch. A bare "fold
it" leaves the session to improvise the part most likely to lose work.

**If the outcome changes a plan**, say how the manifest gets updated: edit
`plan.yaml` directly if this session stewards that plan, otherwise propose it on
the plan's `tracking_issue` — `${PLANS_DIR}/README.md`'s "Proposing structural
changes" section governs. Either way the proposal ends with `${SAVE_PLAN_SCRIPT}`
and republishing the dashboard via `/plan-dashboard <plan-id>` in the same turn,
so no published dashboard is older than the manifest behind it.

**If the outcome is a new item**, the `record` operation of
`"${BASSTLER_PYTHON}" -m "${PLAN_ITEM_BOOTSTRAP_MODULE}"` writes its `plan.yaml` entry and `roadmap.md` section and runs the save
for you — `record` only, never `open`, which creates the branch and pull request
this skill does not.

Flag explicitly, never silently paper over:

- A candidate branch that could not be fetched, so its overlap is unknown
  rather than empty.
- Paths that had to be guessed rather than derived in step 1.
- A duplicate-intent match you are unsure about — say what looks the same and
  let the user settle it.
- A covering plan step 5 ruled out for being full — name it and its item count,
  so the user can see why the work landed in a new plan instead.

Do not touch git, create a branch, or write any code in this skill — its only
output is the plan itself.

Carrying the outcome out later follows [`manifest-staleness.md`](../plan-dashboard/manifest-staleness.md).
