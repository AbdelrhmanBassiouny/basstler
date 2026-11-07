PR: https://github.com/AbdelrhmanBassiouny/basstler/pull/155 (draft, bug, patch)

Plan
- Fix main's failing contract test; release only after Tests pass on main.

Done
- Contract test counts real module invocations only; template header names no module.
- release.yml follows Tests via workflow_run, tags the tested commit on success only.
- Push to main always runs the test matrix, budget aside.

Next
- Wait for PR CI; user to review and merge.
