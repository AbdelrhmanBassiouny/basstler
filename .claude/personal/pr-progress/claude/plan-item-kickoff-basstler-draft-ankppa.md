### Plan
- A blocking dependency chip carries its draft pull request's REST address
- A not-started item blocked only by draft dependencies renders a hidden Start now button
- The site page's script re-checks those pull requests and shows the item as startable
- Playwright (owner-approved) tests the script against a stubbed GitHub API; CI installs Chromium

### Done
- Draft PR #116 opened, item recorded in progress

### Next
- Tests first, then the chip, the action and the script
