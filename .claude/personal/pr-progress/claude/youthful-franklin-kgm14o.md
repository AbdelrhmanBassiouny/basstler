Plan
- Wait for discussion on #152 and review of draft PR #170; adjust the design if replies ask for it
Done
- Proposal posted on #152; draft PR #170 opened (label bug, patch release)
- Build accepts optional notes_token secret (GH_TOKEN + gh auth setup-git); site workflow passes PLAN_SITE_NOTES_TOKEN
- Publication checks registry/notes privacy: missing token writes nothing, unreadable writes and reports
- Tests added; plan_site suite green; pre-commit passes (89a00df)
Next
- Respond to #152 replies and review comments when they arrive
