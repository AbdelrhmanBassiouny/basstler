#!/bin/bash
# A pre-push hook standing in for another writer: before each push it sees, until its
# count of writes runs out, it pushes a commit of its own to the notes branch, so the
# push it precedes is rejected as no longer a fast-forward.
#
# CONCURRENT_WRITER_CHECKOUT names a clone of the notes branch; the count of writes left
# is in writes-remaining inside its .git directory. Anything already committed in that
# clone goes out with its first write.
set -euo pipefail

writer="${CONCURRENT_WRITER_CHECKOUT:?}"
remaining_file="${writer}/.git/writes-remaining"
remaining="$(cat "${remaining_file}")"
[ "${remaining}" -gt 0 ] || exit 0
printf '%s\n' "$((remaining - 1))" > "${remaining_file}"

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY
git -C "${writer}" commit --quiet --allow-empty -m "Another writer's save"
git -C "${writer}" push --quiet origin HEAD
