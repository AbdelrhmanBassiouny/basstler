PR https://github.com/AbdelrhmanBassiouny/basstler/pull/6 (draft): workflow-cutover's plan-site-builder. basstler.build_site renders hub / <owner>/<repo>/ / <owner>/<repo>/<plan>/ from the registry's hub file; session start prints the plan site line.

Plan:
- Site served by stack-board's Pages (plan-site-action, next item). Pages-in-Python split out as site-pages-in-python, pending the owner's confirmation.

Done:
- 7651471 answers the owner's 37-thread review (reuse, shared bases, enum-driven tests); 883 tests pass; replied on every thread, resolved 34; description and plan updated.

Next:
- Owner decides the 3 open threads: dashboard.html (split vs fold in), build_site.py:147 and :163 (unify the pull request classes or keep them separate).
- Live full-site build needs a session with API access to the CRAM repository.
