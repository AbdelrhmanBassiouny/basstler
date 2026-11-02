# basstler session rules

These hold in every session that uses basstler's skills, whichever skill is running.

## A denied command is a question for the user

When the permission system or its classifier denies a command or tool call a skill needs:

- Ask the user with `AskUserQuestion` at once, before going on with anything that depends on it. Name the exact command, what it changes (which branches it pushes, which files it writes) and why the skill needs it.
- Run it, unchanged, once they accept. If they decline, carry on without it and record what is left undone where the skill keeps its record.
- Never work around the denial with a different command that has the same effect, and never drop the step. Listing it at the end of a report as left over is dropping it.
