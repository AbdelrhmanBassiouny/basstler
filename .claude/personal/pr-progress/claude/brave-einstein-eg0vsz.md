Item: plan-dashboards / split-build-dashboard - PR #66 (draft).

**Plan**
- Verbatim move of build_dashboard.py into pull_request_state, dashboard_plan, plan_dependencies, plan_validation, plan_command_arguments, dashboard_cards; renderer + main stay.
- Validation exceptions in basstler/exceptions.py (item notes; departs from *_errors.py precedent).

**Done**
- Source + test split pushed (e6f9835); 1243 pass; rendered dashboard byte-identical; docs repointed.

**Next**
- Watch CI on #66; answer review. #46/#47 re-port onto the new modules if they land second.
