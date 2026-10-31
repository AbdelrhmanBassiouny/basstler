Plan
- PR #96 (draft, release:minor): board export reads the upstream's open PRs through the fork's upstream-reviews Action in cloud sessions; --upstream-read, exit 12.
- #83 carries the add_repo access:"push" wording; whichever of #83/#96 lands second merges export_board and the skill paragraph.
- Follow-up after #83: Branch holds a PullRequest instead of copying its fields (review thread on #84).

Done
- #96 opened from main; full suite 1719 passed.
- #83: merged main (incl. #84), fixed attach wording; 1733 passed; pushed 908721a.

Next
- Adding mcp__claude-code-remote__add_repo to the skills' allowed-tools was blocked by auto mode; the user decides.
- Wait for CI and review on #96 and #83.
