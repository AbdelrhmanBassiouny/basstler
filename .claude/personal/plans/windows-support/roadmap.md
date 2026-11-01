# windows-support - standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- Each fix is a bug PR off main with the bug label, fixing one root cause, proven first by a failing test that mocks the platform where Linux CI cannot reproduce it.
- No fix introduces a new bare program name in a subprocess call: a program is resolved to a full path once, on the class that owns running it.
