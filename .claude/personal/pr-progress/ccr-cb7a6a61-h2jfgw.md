PR #130 - report an unreadable plan site as not verified, never as set up.

Plan
- Make the plan_site check and the setup skill report the plan site truthfully.

Done
- unverified status (exit 1), per-repository token state, run history, recorded site,
  basstler_version row, skill + summary updates, tests (96488d8).
- A token stored after the latest failed run is unverified (728f101).
- Review rounds 1-2 (1f8c991, bc9677f, d007cf2): rename, publication on cyclopts,
  SiteRepository.recorded_on, GitHub refusals name their credential, CredentialOrigin
  base shared by GitHubCredentialVariable and CredentialProvider. All 8 threads resolved.

Next
- Await CI and further review.
