# actions-budget — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- No workflow has a `schedule`: every pipeline runs on events only.
- Draft pull requests run the changed libraries plus their dependents. The full matrix runs on ready for review, a `full-ci` label or dispatch.
- Take the fastest route to unblocking and keep it clean. Prevent a repeat, and add monitors and warnings that fire when rates are being exceeded.
