**Plan**
- Wait for your answers on the 5 open threads (URL type, commit-id type, branch wording x3).

**Done** (2026-10-24 review round, pushed 044ade0)
- Main merged (#33). 22 threads answered inline; 17 resolved.
- Split into flat `upstream_reviews_*` modules (<430 lines); constants/functions onto classes;
  jinja templates; shared `GitCommandRunner`; one `UpstreamReadRequest.report`;
  `nonce` -> `request_identifier`; `WorkflowRun` typed. Suite: 1101 passed.

**Next**
- CI on 044ade0; act on your replies to the open threads.
