## Plan
- Keep #185 to one root cause: a repository the token is not granted shows a warning; any other failed read fails the build.

## Done
- 16942d9: `LivePullRequests` replaces the parallel pull-request and read-failure fields; tests split by module.
- ad6dbef (failing tests) and f6b542c: only a 404 or 403 becomes a warning, which always names `PLAN_SITE_READ_TOKEN`; a 401, 5xx or no answer is raised and fails the build.
- Two field threads replied to and resolved; full suite at f6b542c: 2506 passed, 1 skipped.

## Next
- User's answer on the open file-size thread: split `plan_site/__main__.py`, `publication.py` and `dispatch_check.py` as a separate plan item or not.
- Read CI at f6b542c.
