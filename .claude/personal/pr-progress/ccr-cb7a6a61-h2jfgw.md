PR #130 - report an unreadable plan site as not verified, never as set up.

Plan
- Make the plan_site check and the setup skill report the plan site truthfully.

Done
- unverified status (exit 1), per-repository token state, run history, recorded site,
  basstler_version row, skill + summary updates, tests (96488d8).
- A token stored after the latest failed run is unverified (728f101).
- Review round 1 (1f8c991, bc9677f): TOKEN_STORED_AFTER_FAILURE rename, publication on
  cyclopts, SiteRepository.recorded_on, GitHub refusals name their credential
  (GitHubCredentialRejected for 401), UnreadableDispatch holds only the failure,
  gh's --repo kept. All 7 threads resolved.

Next
- Await CI and further review.
