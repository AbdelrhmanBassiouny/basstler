PR #73 - windows-support / windows-environment-interpreter.

Plan:
- Failing test: environment with only Scripts/python.exe -> BASSTLER_PYTHON resolves to it (layout-mocked, like tests/test_bash.py).
- Fix: interpreter is whichever of bin/python or Scripts/python.exe exists (bin/python before creation); re-resolve after creation.
- uv from pip --target: check bin vs Scripts on Windows.

Done:
- Bootstrap branch + draft PR; split py/python candidates into windows-interpreter-candidates (issue 70 comment).

Next:
- Write failing test in tests/hooks.
