Plan:
- Draft PR #32 (bug): release = tag on the merge commit; no version in any file (hatch-vcs), labels pick minor/major, hook installs latest tag

Done:
- Rework pushed (8a723af); full suite 977 passed; PR description updated

Next:
- Owner creates labels release:minor / release:major, reviews/merges #32
- After merge: confirm the release run tags v0.1.6 and a new session installs @v0.1.6
- CLAUDE.local.md's "Every PR decides its release" rule still names `bump --part`; should become the labels
