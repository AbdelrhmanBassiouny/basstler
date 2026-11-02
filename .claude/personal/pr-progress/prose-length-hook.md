## Plan
- Answer the review on #126: docstrings on every flagged class, field and method
- Move the check into `basstler.code_rules`; copy krrood's AGENTS.md generator (rules as Python `Section` enums) and cite krrood with `:cite:`
- Add `CodeRuleChecker`, the base every checker shares, and link each checker to its rule (`AgentRule.checker`)
- Add a missing-docstring checker (`@override` methods exempt) and a prose-length checker; one cyclopts command `basstler code-rules` with `check` / `agents-md`
- AGENTS.md generated from the rules; "docstrings are always there" rule

## Done
- (nothing yet)

## Next
- Implement, test, push, reply on threads
