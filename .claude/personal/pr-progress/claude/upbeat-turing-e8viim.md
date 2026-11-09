## Plan
- One package environment per project under `$BASSTLER_HOME/environments`; session start exports it and removes those whose project is gone

## Done
- Implemented with tests (f337c01); tests isolated from machine state (8a82513)
- Dropped the uv-workspace dependency from the item (posted on #39); labelled release:minor
- Old shared `venv` left in place for older plugins; README says when to delete it

## Next
- Review on #181; plan site rebuild needs AbdelrhmanBassiouny/stack-board attached to the session
