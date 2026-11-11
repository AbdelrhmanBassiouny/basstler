## Plan
- Live recount of hub and repository cards from one pull request listing per repository

## Done
- Cards carry `counted_items`; stage table derived from `Item.reached_stages`
- Shared `site_live_state.js`; `site_live_progress.js` recounts and rewrites marked spans and bars
- 9 new tests; full suite 2569 passed at b130a2f; ruff and code-rules pass

## Next
- Read CI on b130a2f
- Owner review: script payload keys spelled in JS, URLs derivable from `pull_request_reference`
