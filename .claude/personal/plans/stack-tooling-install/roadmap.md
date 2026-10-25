# stack-tooling-install — standing rules

- The upstream promotion is a separate manual step from the fork-internal merge, so a gate phrased as "on upstream main and fork main fast-forwarded" is not met by a fork merge alone.
- A cross-fork pull request's base-repository CI run has only one remote, pointing at the upstream, so there are zero fork candidates and a configuration load that treats that as an error fails in CI and nowhere else.
