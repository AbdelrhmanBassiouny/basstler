# Sourced (not executed) by session-start.sh, create-personal-notes-branch.sh
# and save-personal-notes.sh, so all three resolve the personal-notes remote,
# branch and path with the exact same precedence: git config > environment
# variable > the zero-config default. See ./README.md.

NOTES_REMOTE="$(git config --get claude.personalNotesRemote || true)"
NOTES_REMOTE="${NOTES_REMOTE:-${CLAUDE_PERSONAL_NOTES_REMOTE:-origin}}"

NOTES_BRANCH="$(git config --get claude.personalNotesBranch || true)"
NOTES_BRANCH="${NOTES_BRANCH:-${CLAUDE_PERSONAL_NOTES_BRANCH:-claude/personal-notes}}"

NOTES_PATH="$(git config --get claude.personalNotesPath || true)"
NOTES_PATH="${NOTES_PATH:-${CLAUDE_PERSONAL_NOTES_PATH:-.claude/personal/cram-notes.md}}"

# NOTES_REMOTE may be either a configured remote's name (e.g. "origin") or a
# raw git URL (e.g. "https://github.com/<you>/<repo>") - `git fetch`/`git
# push` accept both interchangeably, and a URL needs no `git remote add`
# first. Use a URL whenever your own fork isn't the clone's "origin" (for
# example, some session environments name the upstream repo "origin" and your
# fork something else) - the URL form works without depending on that
# session-specific remote name/alias existing at all.
