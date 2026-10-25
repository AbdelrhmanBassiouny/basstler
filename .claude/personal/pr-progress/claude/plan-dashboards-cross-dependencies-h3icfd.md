# claude/plan-dashboards-cross-dependencies-h3icfd - PR #17
`cross-plan-dependencies` in `plan-dashboards` (#34), resolved in `auto` mode.

## Plan
- Cross-plan references, resolved on the plan site; chips link to their dependency's card.

## Done
- Review round 2 (15 threads): rustworkx graph, PlanValidator, functions moved onto classes,
  DependencyReadiness/DependencyChip hold their Dependency, PlanCommandArguments, Plan item index.

## Next
- Waiting on review. Open threads by design: file size (-> split-build-dashboard item),
  DependencyReference existence check (explained), stub files (explained).

## Outstanding
- After this lands, convert the cross-plan blockers recorded in other plans into
  `<plan-id>/<item-id>` references.
- try/except kept in is_publishable and PullRequestRecord.parse_by_repository; removing them
  changes their error contract - user's call.
