Plan:
- Await CI and review on draft PR #194

Done:
- Failing tests first (2e65b4e), then the fix (27600d8): the site repository is read through the API; 404 means create, other refusals raise SiteRepositoryUnreachableError with the reason and SiteAccess.remedy; git failure raises GitCommandFailed
- SiteAccess takes retry_command and attachment_benefit; GitHubResponse.is_not_found
- Full suite green except the 10 Playwright tests the container's Chromium cannot run

Next:
- Check CI (Playwright page tests run there)
