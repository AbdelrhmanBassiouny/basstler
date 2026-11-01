# stack-tooling-install — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- The upstream promotion is a separate manual step from the fork-internal merge, so a gate phrased as "on upstream main and fork main fast-forwarded" is not met by a fork merge alone.
- A cross-fork pull request's base-repository CI run has only one remote, pointing at the upstream, so there are zero fork candidates and a configuration load that treats that as an error fails in CI and nowhere else.
