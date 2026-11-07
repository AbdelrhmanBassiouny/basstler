## Plan
- Expire `RetiredSkill` entries with the next major release (asked on #150's thread); draft PR #159, patch.

## Done
- Entries record their retiring major (3); the check skips older majors; a test fails once a later major is tagged; CI fetches tags (0fbadb38).
- Replied on #150's `RetiredSkill` thread pointing at #159, left open.

## Next
- CI at 0fbadb38 not read. After #159 lands, resolve #150's thread.
