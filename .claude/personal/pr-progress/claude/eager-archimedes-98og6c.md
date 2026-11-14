PR https://github.com/KAOS-repositories/basstler/pull/219 (draft, stacked on #215)

Plan
- Plan site builds its token form with FineGrainedTokenForm; drop its own enums and token_page.

Done
- RepositoryPermission.ACTIONS, FINE_GRAINED_TOKEN_PAGE, SiteRepository.token_form_url on FineGrainedTokenForm.
- Test adjusted with the user's approval; ruff, code rules, suite pass (only Playwright errors).
- Pushed, draft PR opened.

Next
- Wait for review or CI; retarget to main once #215 merges.
