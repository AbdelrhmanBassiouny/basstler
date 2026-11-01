### Plan
- A blocking dependency chip carries its draft pull request's REST address
- A not-started item that only drafts hold back renders a hidden Start now button
- The site page's script re-checks those pull requests and shows the item as startable
- Playwright (owner-approved) tests the script against a stubbed GitHub API, with Chromium installed in CI

### Done
- All of the plan, pushed to draft PR #116, labelled release:minor
- Full suite passes (1914); ruff check and format are clean

### Next
- Wait for CI on #116 (the first run that installs Chromium) and for review
