# work-recommender — standing rules

- Plans stay in plan.yaml (basstler-v3-plans is deferred). Once basstler-v3 (#99) lands, build every item here on v3, not v2: pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- Every ranking rule comes from priorities.yaml; the recommender hard-codes no repository, plan or topic name.
- The recommender reads plans and live state through the existing models (plan_model, the dashboard's pull-request state); it adds no second parser.
- It renders on the site only; there is no Artifact version.
- Effort is counted in size-bucket points, never in item counts; shares and meters are weekly, the queue is daily.
- Each stage of a PR that needs the owner is its own task; waiting on someone else is a state, never a queued task or a counted point.
- Ships as the opt-in basstler-recommender distribution (basstler-packages), never in DefaultPlaybook: its ranker and policy model are general, so team-repository/malloche ranks with it too; the PhD focus, thesis meter and reading and writing slots are the owner's configuration and own playbook. Item kind lives in basstler-plan; focus and leverage are ItemAttribute and panels SitePanel components.
