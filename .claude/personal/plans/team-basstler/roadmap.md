# team-basstler — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- Nothing runs on a schedule: the plan service changes pages from GitHub's webhook events and re-reads live state when a page opens (basstler-service).
- Every piece of team state lives in the team repository: shared plans on its default branch, each member's notes on their own notes/<login> branch, items as its issues. Cross-repository access is the team's Basstler App installation; nobody stores a personal access token.
- One source per fact: plan.yaml owns structure, status and notes; the issue owns the responsible person and discussion; GitHub owns pull request, CI and review state. Nothing copies one into another.
- An item is ready to start only when every dependency is merged or is an open pull request marked ready for review; a draft dependency blocks it.
- A solo setup keeps working unchanged: every team setting defaults to the personal notes.
- Site work lands as shared rendering in basstler.build_site; no further work on the Artifact-only dashboard.
- Each team serves its plan site from its own plan service instance with its own Basstler App; setup automates every step it can and asks for the rest interactively, one short copyable line each.
