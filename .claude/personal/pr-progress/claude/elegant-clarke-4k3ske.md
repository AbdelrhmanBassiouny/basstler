## PR progress: skill-document-links (#74)

Plan
- Test first: no skill document cites a shell variable whose value is a .md document; every skill document's links resolve
- Replace the 21 `${*_DOCUMENT}` references with relative links
- Drop the five unused variables (keep PLAN_SCHEMA_DOCUMENT: check-setup.sh)

Done
- Branch, draft PR #74, manifest recorded in progress

Next
- Write the failing tests
