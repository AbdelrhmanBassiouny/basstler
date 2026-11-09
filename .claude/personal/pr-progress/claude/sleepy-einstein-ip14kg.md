## Plan
- Notes-repository access check (`basstler.personal_notes.access`), reported by session-start.sh and save-plan.sh
- Shared attach-or-ask instruction (`basstler.repository_attachment`), used by the plan site too

## Done
- Tests first (failing on old scripts), implementation, session rule; pushed b31b6bf; PR #171 description current, labelled bug
- ruff, docformatter, code-rules pass; full suite green apart from 4 local Playwright browser errors

## Next
- Owner decides on the exit-0 question in both test_session_start.py threads (answered, left open)
