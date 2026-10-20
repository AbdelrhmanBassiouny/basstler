# actions-budget — standing rules

- No workflow has a `schedule`: every pipeline runs on events only.
- Draft pull requests run the changed libraries plus their dependents. The full matrix runs on ready for review, a `full-ci` label or dispatch.
- Take the fastest route to unblocking and keep it clean. Prevent a repeat, and add monitors and warnings that fire when rates are being exceeded.
