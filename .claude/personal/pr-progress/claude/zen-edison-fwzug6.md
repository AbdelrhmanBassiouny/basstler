# claude/zen-edison-fwzug6

## Plan
- Port basstler.plan command lines from argparse to cyclopts; keep commands, options, statuses
- Rest of the item lives in plan cyclopts-migration (#147)

## Done
- manifest_tools, item_brief, item_mode, size_check, size_limits, check_scope_overlap, updates_since_support on cyclopts
- Refusals carry statuses as CommandFailure; unused plan/command_arguments.py deleted
- Full suite green apart from 4 environmental Playwright errors

## Next
- Owner review of #142; read CI on 6189e6de
- On merge, resolve #138's manifest_tools thread
