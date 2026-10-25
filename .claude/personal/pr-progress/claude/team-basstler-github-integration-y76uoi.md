Plan
- team-basstler/site-action (#63): reusable plan-site-build.yml, plan-site.yml caller, notes-branch trigger
- Deploy only when the rendered site differs from the published one (site digest)
Done
- Workflows, PlanSiteTrigger + install-trigger, PackageTemplate shared, site digest + conditional deploy, tests (1187 pass)
- Replied on r4370727926; thread left open on the pull_request-trigger question
Next
- Owner answers: add pull_request events as a trigger (here or new item)?
- Owner merges #63, sets basstler Pages source to Actions, runs Plan site once
- Then install-trigger on the notes branch and point the hub site_url at basstler Pages
