PR #130 - report an unreadable plan site as not verified, never as set up.

Plan
- Make the plan_site check and the setup skill report the plan site truthfully.

Done
- unverified status (exit 1), per-repository token state, run history, recorded site
  in the publication command, basstler_version row, skill + prerequisite + session-start
  summary updates, tests. Pushed as 96488d8; PR is a draft, labelled bug + release:minor.
- Decided: a token stored after the latest failed dispatch run is unverified (no run has
  used it yet), not info. Skill says the next push settles it. Pushed as 728f101.

Next
- Await CI and review.
