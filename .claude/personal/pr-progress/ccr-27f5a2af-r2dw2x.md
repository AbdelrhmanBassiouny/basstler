PR #131 (draft): https://github.com/AbdelrhmanBassiouny/basstler/pull/131

Plan
- Item basstler-reliability/fail-closed-checks; later items tracked in that plan (issue #132).

Done
- Shell configuration fails closed outside a git work tree (exit 78).
- check-setup.sh --only; the stack-pass gate checks stack_upstream alone.
- stack merge-probe decides conflicts with git merge-tree; resolve uses it.
- Skill commands self-contained via basstler.sh and ${CLAUDE_PLUGIN_ROOT}; tests enforce it.

Next
- Owner review of #131.
