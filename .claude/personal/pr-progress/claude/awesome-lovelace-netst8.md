## Plan
- One `site.css`, wave-column plan page, live status/PR/CI/assignee chips, hub and index cards, build-health banner, failing build on an unreadable registry, end-to-end CI test (all in `basstler.plan_site`; Artifact dashboard untouched)

## Done
- Implemented, pushed, PR #106 draft with `release:minor`, description current
- Merged `main` twice: 386b218 (lean-kickoff's `pull_request_source.py` move, both exceptions kept) and 1062c4d (ruff rules; `ruff check .` passes, files ruff-formatted)
- Suite after merge: 1879 passed; the 22 failures fail identically on `main` here (hook tests needing `basstler` on the system `python3`)

## Next
- CI on 1062c4d, then owner review of #106
