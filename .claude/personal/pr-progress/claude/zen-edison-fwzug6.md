# claude/zen-edison-fwzug6

## Plan
- Port basstler.plan command lines from argparse to cyclopts; keep commands, options, statuses
- Rest of the item lives in plan cyclopts-migration (#147)

## Done
- manifest_tools, item_brief, item_mode, size_check, size_limits, check_scope_overlap, updates_since_support on cyclopts
- Refusals carry statuses as CommandFailure; unused plan/command_arguments.py deleted
- 2026-11-08 resolve: merged main (82cd7ab) in as da4d50b. Conflicts were import blocks only, in check_scope_overlap.py (main's RequestedPath, 18a2250) and updates_since_support.py (main's PostedIssueComment, d7207cb); kept both sides
- merge-probe CLEAN at da4d50b against 82cd7ab
- Tests at da4d50b: tests/plan + updates_since + main_failure 389 passed; the other 31 failures/errors are the same 31 that fail on main in this container (hook tests run a system python3 without basstler's requirements; Playwright/Chromium mismatch)
- Left alone: code-rules flags both module docstrings as over 4 lines; that text is main's, already over the limit there

## Next
- CI on da4d50b not read yet; owner review of #142
- On merge, resolve #138's manifest_tools thread
