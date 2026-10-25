Item: plan-dashboards / split-build-dashboard - PR #66 (draft, release:major).

**Plan**
- Split build_dashboard.py by concern (e6f9835), then group the whole package and its tests into topic subpackages (ca1f488), as the user asked.
- A subpackage's command line goes in its `__main__.py` when nothing imports it, so `basstler.stack` and `basstler.maintenance` keep their names.

**Done**
- Pushed through 5867c6f, main (#63) merged in; 1252 pass; rendered dashboard byte-identical; docs, hooks and workflows repointed; PR description and plan notes and item title updated.

**Next**
- Wait for CI on 5867c6f and for review. Open branches that edit the package (#46, #47) re-port onto the new paths if they land second.
