# plan-size-limits — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- The limits live in basstler/src/basstler/plan_size_limits.py (Measure) and are enforced by save-plan.sh and save-pr-progress.sh; raising one is the user's call.
- branch-index.tsv and dashboard-urls.yaml are keyed by plan id; any split or removal of a plan regenerates both, or session-start.sh stops resolving branches and /plan-dashboard mints duplicate pages.
- New modules go under src/basstler/, and hooks run them with "${BASSTLER_PYTHON}".
- plan.yaml keys are spelled only in basstler.plan_model.ManifestKey; no other module declares its own key enum.
- A plan is full at Measure.ITEM_COUNT (landed items pruned), read through plan_size_check; there is no separate size budget.
