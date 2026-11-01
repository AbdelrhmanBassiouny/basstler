# plan-graph — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- One model, read in slices. Every tool reads plans, items and definitions through basstler.plan_graph; a session queries its own neighbourhood rather than loading the graph. The graph is assembled in memory from the manifests and the stores, never written as one file, so it cannot drift from them.
- Declared, then superseded. An item may declare claims before its branch exists, because nothing else is known then. Once the branch has commits, ast-derived definitions are the truth and any difference is a ClaimDrift finding. Everything that can be derived is derived; a declaration is never trusted past the point it can be checked.
- Scripts decide what is decidable and apply every change; a skill only chooses. Each finding carries a closed list of resolutions, the skill picks one, and `plan_graph resolve` carries it out. A resolution no script can apply is not added to the list.
- No model call in the detector. Scoring is deterministic, runs in CI and is reproducible; it reports ranked pairs and no verdict.
- Non-Python files are catalogued too. The #110/#106 collision was two sessions building the same markdown artifact under two names.
- Extraction and direction-change are one command, give these branches a new common parent, and the probe runs before any apply: `git merge-tree --write-tree` costs nothing and mutates nothing.
- Writing to feature branches is a deliberate exception for common-parent, approved 2026-09-06. integration-conflict-triage never writes a fix to a feature branch, and that rule stands for the integration build.
- An unreachable repository is unverified, never refused and never satisfied. A save must not fail because another repository's notes cannot be fetched, and must not count that reference as ready.
- #17 owns the reference form `<plan-id>/<item-id>` and stays in plan-dashboards. graph-model builds on it; until it lands no manifest here writes a cross-plan depends_on, since main cannot resolve one.
- Freshness is tied to the dashboard publish and to every save, not to a scheduled Action.
- Every module lives in `src/basstler/`; plan.yaml keys are spelled only in plan_model.ManifestKey, and design.yaml's keys get one enum of their own beside it.
