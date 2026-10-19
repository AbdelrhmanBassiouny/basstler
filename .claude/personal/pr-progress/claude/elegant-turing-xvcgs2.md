PR https://github.com/AbdelrhmanBassiouny/basstler/pull/6 (draft): workflow-cutover's plan-site-builder. basstler.build_site renders hub / <owner>/<repo>/ / <owner>/<repo>/<plan>/ from the registry's hub file; session start prints the plan site line.

Plan:
- Site served by stack-board's Pages (plan-site-action, next item). Pages-in-Python split out as site-pages-in-python, pending the owner's confirmation.

Done:
- Three review rounds answered: 7651471 (37 threads), 7ab3682 (5), 329bb81 (2: reviewed-PR counts on every card and the hub header; PullRequestListState as a specification enum). 894 tests pass; description updated.

Next:
- Owner decides the open threads: dashboard.html (split vs fold in), build_site.py:147 (unify pull request classes), build_site.py:444 (SiteSummary model, asked to discuss), locations.py:243 (_hub.yaml name/location).
- Live full-site build needs a session with API access to the CRAM repository.
