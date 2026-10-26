PR #78 - plan stack-maintenance, item promotion-summaries-and-table (auto mode).

Plan:
- written point summaries (--summaries) prefill the upstream PR; first-paragraph derivation removed
- skill step 2 writes summaries for `basstler.stack next` branches before run-report

Done:
- implementation, tests (6 new), SKILL.md step 2 (e90939e)
- review round 1 (06890d4): description built by PromotionSummary.upstream_description; link reader shared in tests/stack/dataset.py, no abbreviations; both threads replied and resolved
- merged main twice; SKILL.md conflict with #81's cut resolved by keeping a shorter summaries step (1290079)

Next:
- author review of the draft; CI on #78
