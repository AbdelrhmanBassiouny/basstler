PR #131 (draft): https://github.com/AbdelrhmanBassiouny/basstler/pull/131

Plan
- Item basstler-reliability/fail-closed-checks; later items tracked in that plan (issue #132),
  including described-exit-codes and cyclopts-command-lines from this PR's review.

Done
- Shell configuration fails closed outside a git work tree (exit 78).
- check-setup.sh --only; the stack-pass gate checks stack_upstream alone.
- stack merge-probe decides conflicts with git merge-tree; resolve uses it.
- Skill commands self-contained via basstler.sh and ${CLAUDE_PLUGIN_ROOT}; tests enforce it.
- Review (9dc8811a): basstler.stack on cyclopts; merge-probe reads the upstream base from the
  upstream and describes conflicts on stderr; preamble in skills/running-commands.md.

Next
- Owner review of the replies on the six threads; read CI on 9dc8811a.
