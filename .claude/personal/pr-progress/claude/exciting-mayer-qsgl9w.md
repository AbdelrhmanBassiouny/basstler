Plan:
- PluginLocation/PluginSkillLocation members relative to the plugin root; PluginRoot dataclass (from_environment raises PluginRootUnsetError / PluginRootNotADirectoryError; locate)
- Resolve at use, never at import (CI imports the package with no root)
- Migrate the 6 call sites; error suggestions name $BASSTLER_PLUGIN_ROOT/hooks/...
Done:
- Branch, draft PR #76, manifest in progress
Next:
- Failing tests in tests/test_locations.py, then implementation
- Open: why CLAUDE_ENV_FILE export missed the reporter's session (ask user)
