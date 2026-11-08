Plan
- Failing test: publication on a private registry with no notes-token secret writes nothing and reports a pending step
- RepositoryDetails reads `private`; publication checks registry + notes repository, and the site repository's PLAN_SITE_NOTES_TOKEN secret
- plan-site-build.yml: optional notes_token secret, used for GH_TOKEN and git fetch; site workflow template passes it
- ruff, format, code-rules check, pytest; update PR description
Done
- Proposal posted on #152; draft PR #170 opened; item recorded in progress
Next
- Write the failing publication test
