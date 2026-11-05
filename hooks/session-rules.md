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

- When a save prints that the build did not start, call `mcp__claude-code-remote__add_repo` with the site repository it names and `access: "push"`, then run `"${BASSTLER_PYTHON}" -m basstler.plan_site.build_start` again.
- If the attach is refused, ask the user with `AskUserQuestion` to allow it, with "Attach it (Recommended)" first, saying why: every plan save then updates the plan site within a minute, without a stored token.
