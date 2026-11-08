# basstler-packages - standing rules

- Distributions are layered and acyclic: core; git and rules; github; reviews, stack and plan; notes; hub and skills; mcp; then the basstler meta-package. A package imports only the basstler packages its pyproject lists.
- Module paths never change: every distribution ships modules under the basstler.<part> namespace, so imports and python -m entry points survive every move.
- New code from any plan goes in the distribution that owns its subject; a v3 area lives next to its v2 code in the same distribution, and v2-removal deletes it there.
- A reorganization pull request only moves code, never changes behaviour, so in-flight branches rebase across it by rename detection.
- Every distribution is released at the same version from the one tag release.yml puts on the merge commit, and pins its siblings exactly; no file carries a version. A basstler distribution depends on a krrood one, and a krrood one on a basstler one, only through a range (>=X,<next-major), so neither repository's release waits on the other.
- Copied krrood code lives only in basstler-core and basstler-rules, cited with :cite:`krrood`, its module and commit, and listed in NOTICE.
- The customization model is called a playbook; workflow keeps meaning a GitHub Actions workflow.
- Two opt-in distributions sit beside the hub: basstler-graph (plan-graph; plan, git, github) and basstler-recommender (work-recommender's general ranker and priorities policy model). Neither is in DefaultPlaybook; a playbook adds them, and they reach the hub and plan items only through SitePanel and ItemAttribute components.
- Freeze until uv-workspace lands: no new branch starts in plan, plan_site, github or stack; the open pull requests finish and land first, while package-map runs beside them. One that stalls in review is rebased across the moves rather than waited for.
- Every module is placed in a distribution in basstler.package_map by the pull request that adds or moves it; the package-boundary check fails on a module no distribution claims.
- Every value a user's workflow may differ in is a playbook setting whose default is today's behaviour; no owner, branch name, label or stage is hardcoded outside the settings and the default playbook.
- A user customizes basstler by depending on its distributions and declaring a playbook, never by copying its code; whatever a user would have to copy is a missing extension point. The customization items were inspired by LucaKro/basstler_domain_model and LucaKro/GitHubWorkflow, a use case that had to copy parts of basstler to add features of its own; each item's pull request credits it.
