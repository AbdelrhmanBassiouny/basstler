## Plan
- Verify full suite on the move commit, push, update PR description

## Done
- new-crossings follows git renames (--base-commit), wired into tests.yml
- Modules moved into basstler.git / basstler.github; board record half -> github.pull_request_record
- ExternalCallFailed -> basstler.exceptions; CredentialOrigin -> basstler.credential_origin
- Crossings 25 -> 18; CI comparison simulated against main: none new

## Next
- Follow-up candidate: StagedLines (pre-commit code-rules check) also loses renames
