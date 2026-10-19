PR https://github.com/AbdelrhmanBassiouny/basstler/pull/6 (draft): workflow-cutover's plan-site-builder. basstler.build_site renders hub / <owner>/<repo>/ / <owner>/<repo>/<plan>/ from the registry's hub file; session start prints the plan site line.

Plan:
- Site served by stack-board's Pages (plan-site-action, next item). Pages-in-Python split out as site-pages-in-python, pending the owner's confirmation.

Done:
- 7651471 answered the first 37-thread review; 7ab3682 answers the second (5 threads): SiteSection bound to ProgressCard with a new SiteSummary, PullRequestListState.states, PageTemplate removed, _hub.yaml documented. 889 tests pass; description updated.

Next:
- Owner decides the open threads: dashboard.html (split vs fold in), build_site.py:147 (unify pull request classes), build_site.py:444 (SiteSummary model, asked to discuss), locations.py:243 (_hub.yaml name/location).
- Live full-site build needs a session with API access to the CRAM repository.
