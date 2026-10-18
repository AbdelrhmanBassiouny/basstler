PR https://github.com/AbdelrhmanBassiouny/basstler/pull/6 (draft): workflow-cutover's plan-site-builder. basstler.build_site renders hub / <owner>/<repo>/ / <owner>/<repo>/<plan>/ from the registry's hub file; session start prints the plan site line.

Plan:
- Site served by stack-board's Pages (plan-site-action, next item). Hub file plans/_hub.yaml on both notes branches names https://abdelrhmanbassiouny.github.io/stack-board/.

Done:
- 2b0c639 on a599549; 878 tests pass; live build rendered 36 plans from 2 repos. Moved 9 tooling plans from CRAM; CRAM-retirement track added to basstler-package; #160 item deferred (folded into #151); dashboards republished (plan-size-limits' artifact is another account's).

Next:
- Wait for review. Then plan-site-action and plan-site-setup via their Start now buttons.
