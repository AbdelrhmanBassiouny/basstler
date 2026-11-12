**Plan**
- Run the first check before any write, with the requested remote as a transient git setting

**Done**
- Failing test (failed first check leaves git config unchanged), TransientGitSetting, lending runner reuses it
- Draft PR #206, bug label; setup tests pass

**Next**
- Wait for CI and review
