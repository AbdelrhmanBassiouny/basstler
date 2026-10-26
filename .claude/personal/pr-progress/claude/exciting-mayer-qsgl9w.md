Plan:
- Plugin root resolved at use via PluginRoot.locate, never at import; PluginLocation members relative
- Second half: skills export the root themselves if CLAUDE_ENV_FILE cannot carry it (pending reporter)
Done:
- PluginRoot + PluginRootUnsetError/PluginRootNotADirectoryError, all call sites migrated, tests; pushed
- Suite: only the 14 env failures main also has
Next:
- Get the reporter's answer on why CLAUDE_ENV_FILE's export missed the session; then fix skills or close the gap
- Mark PR #76 ready once that half is settled
