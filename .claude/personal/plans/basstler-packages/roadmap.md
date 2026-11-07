# basstler-packages - standing rules

- Distributions are layered and acyclic: core; git and rules; github; reviews, stack and plan; notes; hub and skills; mcp; then the basstler meta-package. A package imports only the basstler packages its pyproject lists.
- Module paths never change: every distribution ships modules under the basstler.<part> namespace, so imports and python -m entry points survive every move.
- New code from any plan goes in the distribution that owns its subject; a v3 area lives next to its v2 code in the same distribution, and v2-removal deletes it there.
- A reorganization pull request only moves code, never changes behaviour, so in-flight branches rebase across it by rename detection.
- Every distribution is released at the same version from the one tag release.yml puts on the merge commit, and pins its siblings exactly; no file carries a version.
- Copied krrood code lives only in basstler-core and basstler-rules, cited with :cite:`krrood`, its module and commit, and listed in NOTICE.
- The customization model is called a playbook; workflow keeps meaning a GitHub Actions workflow.
- Two opt-in distributions sit beside the hub: basstler-graph (plan-graph; plan, git, github) and basstler-recommender (work-recommender's general ranker and priorities policy model). Neither is in DefaultPlaybook; a playbook adds them, and they reach the hub and plan items only through SitePanel and ItemAttribute components.
