## Plan
- One `site.css`, wave-column plan page, live status/PR/CI/assignee chips, hub and index cards, build-health banner, failing build on an unreadable registry, end-to-end CI test (all in `basstler.plan_site`; Artifact dashboard untouched)

## Done
- Implemented and pushed in two commits; PR #106 description is current; draft, labelled `release:minor`
- Full suite: 1763 passed; the 17 failures also fail on `main` here (hook tests needing `basstler` on the system `python3`)
- Rendered in Chromium: light/dark, 1280/390 px, no horizontal scroll

## Next
- Owner review of #106
- Whichever of #106 and lean-kickoff (#97) lands second resolves the `PullRequestSource` move in `plan_site/__main__.py`
