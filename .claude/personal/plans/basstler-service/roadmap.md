# basstler-service standing rules

- The Basstler GitHub App is owned by KAOS-repositories; every team runs its own instance with its own App, and no instance holds another team's key or data.
- The service runs on Google Cloud Run from one container image; the App's private key, webhook secret and client secret live only in Secret Manager.
- Pages change from GitHub's webhook events and are re-read live when opened; nothing polls or runs on a schedule.
- Every GitHub call uses an installation or viewer token minted for that request; no personal access token is stored anywhere.
- A viewer sees a plan only if their own GitHub account can read its notes repository and every repository it tracks.
- The notes branch stays the store of record in git; once plan-write-api lands the service is its only writer.
- Rendering reuses basstler.plan_site's page models; the service adds no second renderer.
- The service depends on Starlette and githubkit, both approved; any further dependency is asked for first.
- Until retire-pages-publication lands, the Pages site keeps publishing unchanged.
