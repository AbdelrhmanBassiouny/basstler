## Plan
- Owner reviews draft PR #210

## Done
- new-crossings follows git renames (--base-commit), wired into tests.yml
- Modules moved into basstler.git / basstler.github; board record half -> github.pull_request_record
- ExternalCallFailed -> core exceptions; CredentialOrigin -> core credential_origin
- Crossings 25 -> 18; full suite 2683 passed (2 version-dependent failures, unrelated)
- Pushed 39eb45a3; description updated

## Next
- Read CI on 39eb45a3
- Follow-up: StagedLines (pre-commit code-rules check) loses renames too
