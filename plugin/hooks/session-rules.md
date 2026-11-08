# basstler session rules

These hold in every session that uses basstler's skills, whichever skill is running.

## A denied command is a question for the user

When the permission system or its classifier denies a command or tool call a skill needs:

- Ask the user with `AskUserQuestion` at once, before going on with anything that depends on it. Name the exact command, what it changes (which branches it pushes, which files it writes) and why the skill needs it.
- Run it, unchanged, once they accept. If they decline, carry on without it and record what is left undone where the skill keeps its record.
- Never work around the denial with a different command that has the same effect, and never drop the step. Listing it at the end of a report as left over is dropping it.

## An answer that was not read is not checked

- Each Bash call starts a fresh shell: source the configuration in the same call that uses what it defines. An empty variable means it was not set in that call, never that something is not installed.
- An empty value, an `unknown` state, a non-zero exit or a command run from the wrong directory is *not checked*, never a pass. Re-run it from the project's checkout before reporting it.
- Decide a pull request's conflicts with `basstler.sh stack merge-probe`, never from GitHub's `mergeable_state`.
- Record an item as green, approved or free of conflicts only once this run read it so, naming the commit it was read at.

## The plan site's repository is attached in a cloud session

A plan save starts the plan site's build itself, with this session's credential (`basstler.plan_site.build_start`). In a cloud session that works only once the site repository is attached:

- When the session-start summary's `plan site` line says a plan save cannot start the build yet, attach the site repository it names before the first save: call `mcp__claude-code-remote__add_repo` with it and `access: "push"`.
- When a save prints that the build did not start, attach it the same way, then run the command the save names, `"${BASSTLER_PYTHON}" -m basstler.plan_site.build_start`. Saving again does not retry it: a save with no changes starts no build.
- If the attach is refused, ask the user with `AskUserQuestion` to allow it, with "Attach it (Recommended)" first, saying why: every plan save then updates the plan site within a minute, without a stored token.

## Every pull request keeps a plan, what is done and what is next

- For every pull request you create, keep the PR-progress section of `CLAUDE.local.md` (the block between the `BEGIN-PR-PROGRESS` and `END-PR-PROGRESS` markers, which the session start fills) current as three short lists - Plan, Done, Next. Start it with a short plan as soon as real work on the pull request begins, replace finished steps rather than accumulating them, and update it whenever the plan or your task list changes and before ending a turn that changed either.
- Run `"${BASSTLER_PLUGIN_ROOT}/hooks/save-pr-progress.sh"` whenever it changes.
- Never write it into a file tracked on the pull request's branch: it lives on the personal-notes branch and is never merged.

## An approved plan that spans several pull requests becomes a persistent plan

The moment a plan-mode plan is approved, before implementing, judge whether the work spans several pull requests, branches or sessions. If one pull request in this session contains it, implement it and go no further.

- If no plan covers it, run `/plan-create <plan-id>` with the approved plan as its source: the skill accepts a freeform plan that lives only in this conversation.
- If a plan covers or extends it, ask what the change should be rather than deciding alone, then edit `plan.yaml` and run `"${BASSTLER_PLUGIN_ROOT}/hooks/save-plan.sh"` - see `skills/plan-create/plan-schema.md`, "Proposing structural changes".

This moment decides whether the plan is kept or lost when the session ends.
