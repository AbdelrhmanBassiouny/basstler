## Plan
- Each plan item carries recommended_model (opus, sonnet, haiku), set from the task's difficulty by plan-create and add-plan-item
- The plan site preselects it on the item's action buttons; no per-skill TOML

## Done
- Draft PR #209: field, validation, record/update --recommended-model, page preselection, skill docs, tests; merged main
- Item notes in plan.yaml rewritten for the new design

## Next
- Review; confirm the difficulty guidance in plan-schema.md; label release:minor
