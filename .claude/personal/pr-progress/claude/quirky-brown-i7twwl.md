# artifact-path-retirement (#115)

## Plan
- One helper for a plan's site page URL; session-start, save-plan.sh and item_bootstrap print it
- Skills and starter notes: every "republish /plan-dashboard" step prints the site link instead
- /plan-dashboard keeps the manifest sync and report; drops Artifact publish (step 3) and index mode
- Remove the dashboard-URL cache, record_url, check-publication, the index page command
- Ask the owner before deleting the published Artifacts (irreversible), after merge

## Done
- Bootstrap: branch, draft PR, item in progress

## Next
- Tests for the site-page URL in save-plan.sh and item_bootstrap
