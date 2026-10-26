PR #81 - stack-maintenance / maintenance-skill-steps-only (auto mode, base main).

Plan:
- SKILL.md steps only; rationale in docs/stack/maintenance-pass.md.

Done:
- SKILL.md 16.6 KB -> 5.8 KB; maintenance-pass.md written, linked from README.
- Review round 1 (6278933): main merged; in-review/Workflow-tool wording; 403 found stale (REST base PATCH works) and docs updated. 3 threads resolved.

Next:
- Open threads wait on the plan items executor-side reparenting (r4376633783) and withhold-on-github-state, which removes needs-resolution, after #77 (r4376683912).
- Whichever of #77/#78/#81 lands later carries the others' skill edits into the shorter file.

