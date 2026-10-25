Plan (windows-support / windows-bash-resolution, draft PR #71):
- Resolve bash once (basstler.bash.Bash) so Windows never starts WSL's System32 launcher.

Done:
- Bash.locate: CLAUDE_CODE_GIT_BASH_PATH, else first bash on PATH, else Git Bash beside git; refuses %SYSTEMROOT%; BashNotFoundError.
- All six bare-bash call sites switched; unit + full-setup stub tests; full suite green locally.

Next:
- Wait for CI and review on #71; next plan items: windows-environment-interpreter, setup-report-strict-parsing.
