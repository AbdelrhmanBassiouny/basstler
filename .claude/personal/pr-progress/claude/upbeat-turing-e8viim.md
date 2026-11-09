## Plan
- Key the package environment by project: `$BASSTLER_HOME/environments/<project>-<checksum>`, project = main working tree of the session's project directory
- Session start exports the environment's directory so every command in the session (any attached repository) uses it
- Per-environment install lock; each environment records its project directory
- Session start removes environments whose project directory is gone (never the current or a locked one)
- Tests first in tests/hooks/test_session_start.py; docs (SETUP.md, hooks/README.md)

## Done
- Kickoff: owner chose per-project over per-release, no retention period; base main (uv-workspace dependency not ready, not needed)

## Next
- Failing tests for the per-project location, the export, and the removal
