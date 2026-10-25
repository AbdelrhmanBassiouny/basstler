PR #73 - windows-support / windows-environment-interpreter.

Plan:
- Interpreter = Scripts/python.exe if present else bin/python, set in resolve_basstler_python (re-run after creation).

Done:
- Two layout-mocked tests (failed first), fix, pushed 4318f65; uv path checked (pip --target uses bin on Windows too), no change.
- Candidates split into windows-interpreter-candidates (issue 70 comment).

Next:
- main is red: test_runs_every_hook_script_in_the_bash_claude_code_is_configured_with (#57 sync's bash -c vs #71's expected list); the owner decides on the test change.
- Await review; PR stays draft.
