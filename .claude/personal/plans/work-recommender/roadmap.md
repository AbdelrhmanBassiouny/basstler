# work-recommender — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- Every ranking rule comes from priorities.yaml; the recommender hard-codes no repository, plan or topic name.
- The recommender reads plans and live state through the existing models (plan_model, the dashboard's pull-request state); it adds no second parser.
- It renders on the site only; there is no Artifact version.
