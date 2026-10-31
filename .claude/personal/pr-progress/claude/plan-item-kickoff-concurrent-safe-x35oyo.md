# concurrent-safe-save (#98)

## Plan
- basstler.plan.merge: three-way merge per top-level field, item and roadmap; refuse a part both writers changed.
- save-plan.sh --read-at/--attempts: merge onto the fresh tip, retry a rejected push.
- item_bootstrap passes --read-at and confirms by merge semantics.

## Done
- All of the plan, tests first; full suite 1740 passed; pushed 36e1849; PR description current, labelled release:minor.

## Next
- Owner review: the default of 5 attempts; whether a pruned cross-plan dependency should stop failing validation (flagged in the PR, not fixed here).
- Mark ready for review once reviewed.
