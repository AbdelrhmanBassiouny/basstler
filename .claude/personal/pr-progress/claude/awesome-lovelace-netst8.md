## Plan
- One `site.css` with light/dark tokens, phone width, written once to the site root and linked from every page
- Site plan template: one column per wave, cards with status, PR, CI and assignee chips plus dependency hints
- `PullRequestRecord` gains the head commit and assignees; CI read via `GitHubRepository.check_state` for open PRs only
- Hub and repository pages as cards with progress
- Build health: a banner naming skipped plans and unreadable repositories; an unreadable registry raises and fails the build
- End-to-end CI test building the site from the test dataset

## Done
- Kickoff: draft PR #106 opened, manifest recorded as in progress

## Next
- Write failing tests for the stylesheet file and the health record, then implement
- Keep the `PullRequestSource` edits small: lean-kickoff (#97) moves it to `pull_request_source.py`
