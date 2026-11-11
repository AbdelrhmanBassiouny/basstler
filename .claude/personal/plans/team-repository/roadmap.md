# team-repository — standing rules

- Plans stay in plan.yaml. Once basstler-v3 (#99) lands, build every item here on v3, not v2: pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- Nothing runs on a schedule: every push to a notes branch starts the site build through its dispatch workflow, and a manual run is always possible; a build deploys only when a rendered page changed.
- Every piece of team state lives in the team repository: shared plans on its default branch, each member's notes on their own notes/<login> branch. The one cross-repository credential is each user's fine-grained PAT: Actions write on their site repository and Contents read on the repositories it lists.
- A team site reads only the team repository and the upstream's pull requests, never members' forks: a fine-grained token cannot read another user's private fork, so one read-only token for the organization covers the whole site. A pull request still only on a member's fork shows on that member's own site until it is promoted.
- One source per fact: plan.yaml owns structure, status and notes; GitHub owns pull request, CI and review state. Nothing copies one into another.
- An item is ready to start only when every dependency is merged or is an open pull request marked ready for review; a draft dependency blocks it.
- A solo setup keeps working unchanged: every team setting defaults to the personal notes.
- Site work lands as shared rendering in basstler.plan_site (the basstler-hub distribution); no further work on the Artifact-only dashboard.
- The plan site builds in a repository the user owns, never on a project repository; setup automates every step it can and asks for the rest interactively, one short copyable line each.
