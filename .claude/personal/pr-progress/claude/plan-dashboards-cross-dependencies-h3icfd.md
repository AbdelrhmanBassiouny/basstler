# claude/plan-dashboards-cross-dependencies-h3icfd - PR #17
`cross-plan-dependencies` in `plan-dashboards` (#34), resolved in `auto` mode.

## Plan
- Merge main (136 commits) and port the branch onto it.
- Cross-plan chips link to the site's plan page (`../<plan-id>/#<item-id>`, new tab);
  same-plan chips jump to the item's anchor (review r4370633002). No URL cache:
  workflow-cutover's rule forbids further Artifact-only work.
- `build_site` hands the renderer the repository's other plans.
- Drop `build_dashboard.ManifestKey` in favour of `plan_model`'s (item notes).

## Done
- Merge started.

## Next
- Resolve conflicts, run the tests, push, update the PR description, reply on the thread.

## Outstanding
- After this lands, convert the cross-plan blockers recorded in other plans into
  `<plan-id>/<item-id>` references.
