Branch restarted from main after PR 5 merged (v0.1.1 released). Now: workflow-cutover's plan-site-builder (a599549 holds the hub part, no PR yet).

Plan:
- Hub file in each repo's notes (plans/_hub.yaml), basstler is the registry. plan_hub/build_hub in Python; indexes and dashboards link up; session start prints the hub line.

Done:
- Moved 9 tooling plans from CRAM notes to basstler (CRAM 8c6c016), carried their dashboard URLs. Published basstler index (GanshUqLJm7MS5z8oChaQ2) and hub (Bn8wrrpCVeL5qdpnVK9SeK); _hub.yaml on both notes branches. 860 tests pass. Recorded plan-site-builder/-action/-setup in workflow-cutover (stack-board-single-site deferred), dashboard republished.

Next:
- plan-site-builder: port build_site from cc27198 (basstler branch claude/plan-dashboard-multi-account-y2vexc) into src/, hub page as site root, drop set-url/Artifact hub bits; draft PR. Then plan-site-action reworks stack-board's plan-dashboards.yml (no cron).
