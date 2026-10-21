# work-recommender — standing rules

- Every ranking rule comes from priorities.yaml; the recommender hard-codes no repository, plan or topic name.
- The recommender reads plans and live state through the existing models (plan_model, the dashboard's pull-request state); it adds no second parser.
- It renders on the site only; there is no Artifact version.
