## PR #56 - /upstream-reviews without committed project files

Plan
- Dispatch basstler's `upstream-reviews-dispatch.yml`; upstream in personal stack.toml, saved by `setup_steps configure-upstream` and checked by check-setup.sh's `stack_upstream` row (`--require-upstream`).

Done
- Workflows, `reviews_repository`, skill, docs, tests, 0.2.0 (`release:minor`).
- Folded in configure-upstream + check row + setup/maintenance skill steps; description and plan notes updated.

Next
- Review on #56 (conflicts with #45 in setup files go to whichever lands second); after merge, verify live from a CRAM session.
