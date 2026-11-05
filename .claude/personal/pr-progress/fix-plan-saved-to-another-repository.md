## PR progress: fix-plan-saved-to-another-repository (#138, untracked bug fix)

**Plan**
- Refuse to save a plan whose default_repository differs from the notes repository it is saved to

**Done**
- PlanInAnotherRepository check, the validate --notes-remote-url option, save-plan.sh wiring and plan-create docs (0f1f5ece); tests first; affected suites green

**Next**
- User: whether the release is a patch or release:minor
