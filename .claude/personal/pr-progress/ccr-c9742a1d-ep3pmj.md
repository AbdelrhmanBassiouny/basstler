## Plan
- `MergeWorkflow` (plan_site/workflows.py): the dispatch workflow's twin, on `pull_request: closed`, job runs only when merged; template extends the dispatch template.
- `WorkflowLocation.PLAN_SITE_MERGE` names its file.
- `PlanSitePublication.publish` writes it onto the notes repository's default branch (same `PLAN_SITE_TOKEN`).
- Tests first: written on the default branch, re-run writes nothing, trigger/condition/step shape, both workflows pass the Actions budget.
- Docs: setup-personal-notes SKILL.md section 8.

## Done
- Bootstrap, draft PR #122.

## Next
- Tests, then implementation.
