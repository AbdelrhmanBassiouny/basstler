Plan
- team-basstler/site-action (#63): reusable plan-site-build.yml, plan-site.yml caller, notes-branch trigger
- Review r4370727926: deploy only when the rendered site differs from the published one (site digest)
Done
- Workflows, PlanSiteTrigger + install-trigger, PackageTemplate shared, tests, draft #63
Next
- Digest file in build_site, compare step in plan-site-build.yml, tests; reply on the thread
- Owner merges #63, sets basstler Pages source to Actions, runs Plan site once
- Then install-trigger on the notes branch and point the hub site_url at basstler Pages
