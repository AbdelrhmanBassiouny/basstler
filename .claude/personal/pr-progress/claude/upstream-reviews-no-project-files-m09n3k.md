**Plan** (resolving #56's 22 review threads, all yours, 2026-10-24)
- Split `upstream_reviews.py` (2561 lines) and the Action, helper, fetch modules into a
  `basstler.upstream_reviews` package of files under ~500 lines; errors in its `exceptions.py`.
- Module-level constants and functions -> classproperties / methods of their class.
- Caller workflow and README -> jinja2 templates (jinja2 is already a dependency).
- Action's own `Git` -> the shared `GitCommandRunner`.
- `nonce` -> `request_identifier`; run conclusion -> `CheckOutcome`; run URL derived from
  `Repository` and the run's id.
- `upstream-reviews-action.yml` header trimmed; the two SKILL.md passages reworded.
- Reply inline on all 22 threads; resolve the done ones, leave questions open.

**Done**
- Merged main (#33).

**Next**
- Implement, run the suite, format, push, update the PR description, back to draft.
