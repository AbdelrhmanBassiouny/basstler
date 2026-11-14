Plan (Windows test failures, draft #220, off main):
- Fix the Windows-only causes of the suite failures, each with a test that fails on Linux CI first

Done:
- WSL bash, cp1252 text, read-only clone removal, backslash AGENTS.md paths: three code rules with
  repository-wide checker tests; Windows run 466 failed + 196 errors -> 161 failed, 0 errors

Next:
- Remaining Windows-only causes: python3 Store stub fallback, str(Path) renders, file:// fork URLs,
  local gh version and credential leaks
