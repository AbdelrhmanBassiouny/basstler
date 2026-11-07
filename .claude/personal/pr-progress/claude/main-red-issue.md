PR: https://github.com/AbdelrhmanBassiouny/basstler/pull/156 (draft, release:minor)

Plan
- One main-red issue while main's tests fail; session-start line. Part 2 (sub-issue) waits for #144.

Done
- Workflow, MainFailureTracker, shared github/issue.py and workflow_run.py models, two agent rules.
- Second review round at d7207cbc: to_json, IssueClosing, IssueComment/PostedIssueComment,
  TestsRunVerdict.from_run_check; five threads resolved.
- Key-enum cleanup recorded as core-robustness/payload-key-models.

Next
- Open threads: verdict on CheckOutcome? (answered, awaiting user); MainFailureTracker shape;
  StrEnum thread stays open until payload-key-models lands.
- CI on d7207cbc not yet read.
