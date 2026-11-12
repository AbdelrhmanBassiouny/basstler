Plan:
- Failing tests: exit status other than 0/1, missing row, unreadable row each raise CheckSetupFailedError carrying status and stderr; the setup command exits CHECK_SETUP_FAILED
- CheckSetupFailedError in setup/exceptions.py; SetupReport.from_completed_process takes the requested checks (all by default, --only tests pass theirs)
- Document exit 5 in setup-personal-notes SKILL.md
Done:
- Branch, draft PR #202, plan item recorded in progress
Next:
- Write the failing tests
