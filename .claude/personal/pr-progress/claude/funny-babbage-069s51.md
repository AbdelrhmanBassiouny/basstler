## Plan
- Lower ActionRead.start_allowance default from 60 to 20, test first.

## Done
- Draft PR #103 opened, `bug` label set.
- Failing test (fake clock, waited == 20), then the one-line fix; pushed.

## Next
- Nothing; awaiting review. 4 tests in tests/maintenance/test_command_line.py fail in this sandbox on main too (subprocess lacks deps).
