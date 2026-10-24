Plan:
- Draft PR #32 (bug): release = tag on the merge commit; no version in any file (hatch-vcs), labels pick minor/major, hook installs latest tag

Done:
- Merged main (v0.1.7); both 2026-10-24 review rounds addressed: VersionPart owns its label, DataclassException, match/case, test runners reused; example caller on @main; AGENTS.md copied from the cram fork's #517; plugin.json kept as (a), (c) planned as basstler-package/plugin-from-installed-package

Next:
- Owner confirms the AGENTS.md thread (which PR 517 was meant)
- After merge: confirm the run tags v0.1.8 and a new session installs @v0.1.8; drop the "Until #32 merges" sentence and the design rule from the personal notes (now in AGENTS.md)
