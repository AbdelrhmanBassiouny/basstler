# team-basstler — standing rules

- Nothing runs on a schedule: every push to a notes branch starts the site build through its dispatch workflow, and a manual run is always possible; a build deploys only when a rendered page changed.
- Every piece of team state lives in the team repository: shared plans on its default branch, each member's notes on their own notes/<login> branch, items as its issues. The one cross-repository credential is each user's fine-grained PAT: Actions write on their site repository and Contents read on the repositories it lists.
- One source per fact: plan.yaml owns structure, status and notes; the issue owns the responsible person and discussion; GitHub owns pull request, CI and review state. Nothing copies one into another.
- An item is ready to start only when every dependency is merged or is an open pull request marked ready for review; a draft dependency blocks it.
- A solo setup keeps working unchanged: every team setting defaults to the personal notes.
- Site work lands as shared rendering in basstler.build_site; no further work on the Artifact-only dashboard.
- The plan site builds in a repository the user owns, never on a project repository; setup automates every step it can and asks for the rest interactively, one short copyable line each.
