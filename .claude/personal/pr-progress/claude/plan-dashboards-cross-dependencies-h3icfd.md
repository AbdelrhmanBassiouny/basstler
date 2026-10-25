# claude/plan-dashboards-cross-dependencies-h3icfd - PR #17
`cross-plan-dependencies` in `plan-dashboards` (#34), resolved in `auto` mode.

## Plan
- Cross-plan references, resolved on the plan site; chips link to their dependency's card.

## Done
- main merged; chips link through build_site's plan_url (no URL cache); build_site resolves
  cross-plan entries; plan_model.ManifestKey only. 1233 tests pass. Description updated,
  release:minor labelled.

## Next
- Reply on review thread r4370633002 and resolve it: blocked by a pending review of the
  owner's own on #17 (one pending review per user).
- Waiting on review.

## Outstanding
- After this lands, convert the cross-plan blockers recorded in other plans into
  `<plan-id>/<item-id>` references.
- is_publishable keeps main's try/except; removing it needs a non-raising validate_plan.
