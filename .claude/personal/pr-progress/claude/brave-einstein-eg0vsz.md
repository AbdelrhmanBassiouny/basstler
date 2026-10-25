Item: plan-dashboards / split-build-dashboard - PR #66 (draft).

**Plan**
- Move build_dashboard.py verbatim into pull_request_state, dashboard_plan, plan_dependencies, plan_validation, plan_command_arguments, dashboard_cards; renderer + main stay.
- Validation exceptions -> basstler/exceptions.py (item notes; departs from *_errors.py precedent).
- Split test_build_dashboard.py to match; callers import from owning module.

**Done**
- Branch, draft PR, manifest in progress.

**Next**
- Source split, then tests, then docs that name build_dashboard.py's classes.
