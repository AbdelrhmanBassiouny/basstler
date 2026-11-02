## Plan
- Review on #126: docstrings everywhere, `basstler.code_rules` (krrood copy, rules linked to checkers), cyclopts

## Done
- 87b8831: `code_rules` subpackage, generated AGENTS.md, missing-docstring and prose-length checkers, `basstler code-rules check|agents-md`, hooks
- 3b976d8: merged main; #125's rule declared as `SHORTEST_DOCSTRINGS` (CI fix)
- ebe1a19: `MiscRules` dissolved into topics; test line numbers in `tests/constants/source_lines.py`
- Resolved 8 threads; cram PR prompt posted on r4442618572

## Next
- Open threads: r4442618572 (cram PR to run, format script move, licence), r4443232456 (hook via `basstler` script: keep, `language: system`, or `.pre-commit-hooks.yaml`)
- krrood as a dev-only dependency: waiting on decision
