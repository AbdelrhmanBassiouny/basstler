**Plan**
- windows-latest job running the setup end to end, only on PRs changing setup code (owner's choice)

**Done**
- windows-setup.yml, Trigger.paths, tests for triggers and path filters
- Draft PR #208

**Next**
- Expect the Windows job to fail until #204, #205 and #206 merge; rebase and read its run then
