# basstler-service standing rules

- basstler is open source and self-hostable: code and docs name no owner, instance or host, which are configuration; basstler's own instance is the Basstler App of KAOS-repositories on Cloud Run.
- Every team runs its own instance with its own App; no instance holds another team's key or data.
- The service is one container that runs on any container host; its key and secrets come from the environment or mounted files, never the repository, and Cloud Run is one deploy target, not a requirement.
- Every dependency is open source under a licence compatible with Apache-2.0, and running an instance needs no proprietary service beyond GitHub.
- Pages change from GitHub's webhook events and are re-read live when opened; nothing polls or runs on a schedule.
- Every GitHub call uses an installation or viewer token minted for that request; no personal access token is stored anywhere.
- A viewer sees a plan only if their own GitHub account can read its notes repository and every repository it tracks.
- The notes branch stays the store of record in git; once plan-write-api lands the service is its only writer.
- Rendering reuses basstler.plan_site's page models; the service adds no second renderer.
- The service depends on Starlette and githubkit, both approved; any further dependency is asked for first.
- Until retire-pages-publication lands, the Pages site keeps publishing unchanged.
