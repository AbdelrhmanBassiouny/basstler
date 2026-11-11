## Plan
- Hold back only for the repositories the registration adds (notes repository + its plans' repositories); warn for the rest
## Done
- Failing test proved #188; fix in publication.py (repositories_with_plans_of) and user_steps.py (holds_back(registered))
- Full suite passes apart from Playwright browser launches in this container; ruff, code-rules, pre-commit pass
## Next
- CI on PR #197, then review
