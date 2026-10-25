# team-basstler — standing rules

- Nothing runs on a schedule: the site rebuilds on a plan push, a pull request event in the registry repository, an issue event in the team repository, or a manual dispatch; a build deploys only when a rendered page changed.
- Every piece of team state lives in the team repository: shared plans on its default branch, each member's notes on their own notes/<login> branch, items as its issues. No cross-repository trigger and no personal access token.
- One source per fact: plan.yaml owns structure, status and notes; the issue owns the responsible person and discussion; GitHub owns pull request, CI and review state. Nothing copies one into another.
- An item is ready to start only when every dependency is merged or is an open pull request marked ready for review; a draft dependency blocks it.
- A solo setup keeps working unchanged: every team setting defaults to the personal notes.
- Site work lands as shared rendering in basstler.build_site; no further work on the Artifact-only dashboard.
