Plan:
- Await CI on 40040b0 and review.
Done:
- Unreadable site repository raises SiteRepositoryUnreachableError with a per-cause fix (SiteReadFailure); replied to review 5863831822.
- Publication's reads retry 4 times, 2 s doubling (30 s); an unavailable GitHub is reported with attempts, time waited and githubstatus.com.
- CI on 27600d8 failed in apt (DNS on the runner), no test ran.
Next:
- Read CI on 40040b0.
