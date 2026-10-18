PR https://github.com/AbdelrhmanBassiouny/basstler/pull/6 (draft): workflow-cutover's plan-site-builder. basstler.build_site renders hub / <owner>/<repo>/ / <owner>/<repo>/<plan>/ from the registry's hub file; session start prints the plan site line.

Plan (resolving the 2026-10-18 owner review, 37 threads, via /plan-item-resolve in auto mode):
- Reuse instead of redefine: ProjectLocation.PLANS/PLAN_HUB, PersonalNotesSetting.BRANCH, PlanDocument, Repository (clone and pull request URLs), GitCommandRunner, PullRequestField (REST keys), PullRequestState.
- Classes over free functions: PullRequestRecord.from_api, PlanHub.from_registry, page classes on one TemplatePage base, one ProgressCard base for plan and repository cards, one SiteSection base for the hub and repository sites; render() returns RenderedDashboard.
- Flatten GitHubPullRequestSource's cache to one dict keyed by PullRequestReference.
- Tests: every literal read from the dataset or from src's enums; an href() helper.
- Building the pages in Python instead of Jinja templates is split out as a new item, site-pages-in-python, and that thread stays open for the user.

Done:
- 2b0c639 on a599549; 878 tests pass; live build rendered 36 plans from 2 repos.

Next:
- Implement the plan test-first, push, reply on each thread, put PR 6 back to draft, update the description.
