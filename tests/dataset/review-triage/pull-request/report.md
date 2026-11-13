## Review triage

**2 of 6 files need review**; the other 4 change only mechanically.

Renames applied - check them once here instead of in every file:

| Old | New | Found by |
| --- | --- | --- |
| `old_name` | `new_name` | diff |

### Needs review

- `added.py`
- `geometry.py`

### Mechanical

| File | Change |
| --- | --- |
| `caller.py` | imports, rename |
| `helpers.py` | rename |
| `notes.md` | rename |
| `package/constants.py` (from `constants.py`) | move |

<sub>Declare a rename the triage missed, or reject one it found, in the description: `<!-- review-triage` then YAML with `renames: {old: new}` or `rejected_renames: [old]`, then `-->`.</sub>
