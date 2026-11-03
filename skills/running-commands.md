# Running a skill's commands

Run every command as one self-contained Bash call: nothing a call sources or sets
survives into the next, so a block that uses the shell configuration sources it itself.

`${BASSTLER_PLUGIN_ROOT}`, in this and every other document a skill links, is the plugin
root that skill's own `SKILL.md` names. Claude Code substitutes the plugin root only into
a skill's `SKILL.md`, as it loads it; a linked document is read as written, so it names
the root the session start exported instead, and the skill says what that is.
