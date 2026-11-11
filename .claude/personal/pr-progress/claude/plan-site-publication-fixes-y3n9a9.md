Plan:
- Await CI on 5737d30 and review of the per-cause fixes.
Done:
- Tests and fix: unreadable site repository raises SiteRepositoryUnreachableError instead of "create it".
- Review 5863831822: SiteReadFailure gives each cause its own fix (proxy not-attached, credential refused, GitHub unavailable, refusal with own fix); replied on the PR.
- CI on 27600d8 failed in apt (DNS on the runner), no test ran.
Next:
- Read CI on 5737d30; a rate-limit-aware retry only if asked.
