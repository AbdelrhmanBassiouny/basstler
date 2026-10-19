Plan:
- Draft PR #33 (bug): tests pin BASSTLER_PLUGIN_ROOT to the checkout's plugin, so a session's synced plugin root doesn't leak into the suite

Done:
- conftest.py pins the variable; regression test in test_locations.py; 846 passed in a session exporting the synced root

Next:
- Owner reviews/merges #33
