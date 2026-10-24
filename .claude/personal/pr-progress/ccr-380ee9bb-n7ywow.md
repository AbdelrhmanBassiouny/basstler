Plan:
- Draft PR #32 (bug): release = tag on the merge commit; no version in any file (hatch-vcs), labels pick minor/major, hook installs latest tag

Done:
- Merged main (v0.1.7); review round of 2026-10-24 addressed: VersionPart owns its label, MalformedVersion is a DataclassException, match/case, test runners reused, shell function named in ShellConfigurationFunction

Next:
- Owner decides the plugin.json thread (package newer than the plugin copy) and the upstream-reviews.yml pin thread
- After merge: confirm the run tags v0.1.8 and a new session installs @v0.1.8; drop the "Until #32 merges" sentence from the notes
