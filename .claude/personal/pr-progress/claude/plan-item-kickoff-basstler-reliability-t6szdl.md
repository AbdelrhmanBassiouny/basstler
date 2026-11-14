Plan:
- basstler.setup.gate: skill -> required checks mapping, `basstler.sh setup.gate --skill <skill>` runs check-setup.sh --only those
- prerequisite-check.md runs the gate; plan-create, add-plan-item, plan-item-gathering, upstream-reviews name their skill
- tests first: gate arguments, required row blocks, 78 passes through, doc contract

Done:
- PR #216 opened as draft; item recorded in progress

Next:
- write failing tests in tests/setup/test_gate.py
