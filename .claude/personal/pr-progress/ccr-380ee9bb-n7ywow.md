Plan:
- Publish each release tag as a GitHub release from release.yml (draft PR #32)

Done:
- Release step outputs its tag; new step runs gh release create --generate-notes; tests + README updated

Next:
- Owner reviews/merges #32 (merge itself releases v0.1.2, the first with a GitHub release)
- Optional: backfill releases for v0.1.0 / v0.1.1 by hand
