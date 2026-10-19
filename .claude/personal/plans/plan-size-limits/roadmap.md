# plan-size-limits — standing rules

- The limits live in basstler/src/basstler/plan_size_limits.py (Measure) and are enforced by save-plan.sh and save-pr-progress.sh; raising one is the user's call.
- branch-index.tsv and dashboard-urls.yaml are keyed by plan id; any split or removal of a plan regenerates both, or session-start.sh stops resolving branches and /plan-dashboard mints duplicate pages.
- New modules go under src/basstler/, and hooks run them with "${BASSTLER_PYTHON}".
- plan.yaml keys are spelled only in basstler.plan_model.ManifestKey; no other module declares its own key enum.
- A plan is full at Measure.ITEM_COUNT (landed items pruned), read through plan_size_check; there is no separate size budget.
