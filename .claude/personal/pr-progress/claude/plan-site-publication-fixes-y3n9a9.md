Plan:
- Failing tests: a refused site repository read raises instead of asking to create it; 404 still asks; git failure after a successful read raises git's error
- Read the site repository through the API in publish(); add SiteRepositoryUnreachableError; SiteAccess takes the retry command
- default_branch_of raises instead of returning None

Done:
- Branch, draft PR #194 (bug), item recorded in progress

Next:
- Write the failing tests
