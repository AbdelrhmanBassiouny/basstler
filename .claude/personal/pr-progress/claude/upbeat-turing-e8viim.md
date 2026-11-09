## Plan
- One package environment per project under `$BASSTLER_HOME/environments`, keyed by main working tree; per-environment install lock
- Session start exports `BASSTLER_ENVIRONMENT_DIRECTORY` and removes environments whose project directory is gone

## Done
- Owner chose per project over per release, no retention period; based on main (uv-workspace dependency not ready, not needed)
- Implemented with tests (f337c01); full suite green apart from the sandbox's Playwright browser errors, which also occur on main; ruff and code-rules pass
- Docs point by-hand commands at `"$BASSTLER_PYTHON"`

## Next
- Review on #181; owner to decide on removing the old shared `venv` and dropping the uv-workspace dependency
