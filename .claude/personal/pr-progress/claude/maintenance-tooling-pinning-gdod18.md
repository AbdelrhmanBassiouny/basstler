## PR #44 progress

- Merged `main` in; the root-level files conflicted because of the package move, so the branch now equals `main` plus the port.
- #64 replaced the fetch-and-refuse half; what remains is `Stack.effective_parent` (reparent onto the branch carrying a gone parent, `parent-gone` outcome), ported onto `src/basstler/stack` and `maintenance`.
- Decided: `parent-gone` follows the same `ConflictResponse` as a conflict (owner told on a whole-board pass, left to the caller on a named subtree).
- No upstream is configured for this repository, so no upstream review was read.
- Open: apply the `release:minor` label.
