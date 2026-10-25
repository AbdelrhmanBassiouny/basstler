Item: plan-dashboards / split-build-dashboard - PR #66 (draft, release:major).

**Plan**
- Split build_dashboard.py by concern (e6f9835), then group the whole package and its tests into topic subpackages (ca1f488), as the user asked.
- A subpackage's command line goes in its `__main__.py` when nothing imports it, so `basstler.stack` and `basstler.maintenance` keep their names.

**Done**
- Pushed through c186a42: main (#63, #65) merged in, first review round answered and resolved; 1254 pass; rendered dashboard byte-identical; docs, hooks and workflows repointed; PR description and plan notes and item title updated.

**Next**
- Wait for CI on c186a42 and the next review. Open branches that edit the package (#46, #47) re-port onto the new paths if they land second.
