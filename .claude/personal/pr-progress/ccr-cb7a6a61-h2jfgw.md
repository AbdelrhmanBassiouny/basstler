PR #130 - report an unreadable plan site as not verified, never as set up.

Plan
- Make the plan_site check and the setup skill report the plan site truthfully.

Done
- unverified status (exit 1), per-repository token state, run history, recorded site
  in the publication command, basstler_version row, skill + prerequisite + session-start
  summary updates, tests. Pushed as 96488d8; PR is a draft, labelled bug + release:minor.

Next
- Owner to decide: should a token stored after the latest failed run be unverified
  rather than info?
- Await CI and review.
