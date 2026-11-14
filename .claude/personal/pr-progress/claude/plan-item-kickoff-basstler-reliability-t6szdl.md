Plan:
- per-skill setup gates: basstler.setup.gate + skill docs (done, PR #216 draft)

Done:
- GatedSkill mapping, `basstler.sh setup.gate --skill <skill>` running check-setup.sh --only
- prerequisite-check.md and the five gated skills' documents run the gate
- tests: hook scenarios, command-line parsing, document contract; full suite green apart from environmental Playwright errors
- PR description and release:minor label

Next:
- review; resolve any import conflict with #210 when one of them lands
