PR #130 - report an unreadable plan site as not verified, never as set up.

Plan
- Make the plan_site check and the setup skill report the plan site truthfully.

Done
- unverified status (exit 1), per-repository token state, run history, recorded site,
  basstler_version row, skill + summary updates, tests (96488d8).
- A token stored after the latest failed run is unverified (728f101).
- Review round 1 (1f8c991): TOKEN_STORED_AFTER_FAILURE rename, publication on cyclopts,
  SiteRepository.recorded_on / from_dispatch_workflow, test reads runs via RunListing.

Next
- Await owner's answers on 3 open threads: credential explanation on GitHub failure
  classes (+ GitHubCredentialRejected subclass), UnreadableDispatch vs DataclassException
  (recommended: stay a reading holding the failure), cyclopts for gh's --repo (recommended: keep).
