Plan (review-triage/mechanical-file-triage, draft #213; follow-up draft #214):
- #213: extensible basstler-review-triage distribution, CI summary, mark-viewed
- #214: keyword-argument judgment (signature-checked) and module-move rename source

Done:
- #213: judgments, change kinds, rename sources, outputs; open PRs triaged
- #214: tree matcher with rules and findings, callee resolutions, definition records;
  calls resolved through declared attribute and parameter types; CRAM #967 123/154
  mechanical in 15 s, 92 MB; #210 194/246 with 32 module moves; 67 triage tests

Next:
- User runs `basstler review-triage mark-viewed 210` locally (cloud refuses GraphQL)
- Possible: a rename source for definitions moved between modules (#210's importers)
