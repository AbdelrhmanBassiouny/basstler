# bash-to-python — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- Typed invocations land before the conversion items: every conversion rewrites the same subprocess and API calls, so they are written once, in the typed form.
- The conversion items follow the carried bash-touching branches, not lead them: a wholesale body rewrite conflicts with every carried branch.
- basstler-package's standing rules apply here too: https://github.com/AbdelrhmanBassiouny/basstler/blob/claude/personal-notes/.claude/personal/plans/basstler-package/roadmap.md
