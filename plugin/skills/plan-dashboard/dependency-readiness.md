# Checking whether an item's dependencies are ready to build on

Shared by `plan-item-kickoff` and `plan-item-resolve`'s "gather the item's
own context" steps — both need to answer the exact same question ("is it
actually safe to stack new work on top of item X's dependencies?"), so
this procedure lives here once instead of being restated in each skill.

Source the shared config script if you haven't already this session (see
`.claude/skills/plan-dashboard/SKILL.md` step 1 — it defines
`CHECK_DEPENDENCY_READINESS_SCRIPT`, used below):

```bash
source .claude/hooks/resolve-personal-notes-config.sh
```

For the item's `depends_on` list, bulk-fetch every referenced pull
request's live state (per repository referenced):

1. `mcp__github__list_pull_requests` with `state: "all"`, `perPage: 100`,
   paginating (`page`) until a page comes back short of 100.
2. For any dependency whose `pull_request_number` isn't in that result set
   (older than the pagination window covered), fall back to
   `mcp__github__pull_request_read` with `method: "get"` for that specific
   `pullNumber`.

Assemble this into the `pr_data.json` shape `build_dashboard.py` expects —
see its own `--help` / module docstring for the exact format (keyed by
`"owner/repo"`, then by pull request number as a string). Then run:

```bash
python3 "${CHECK_DEPENDENCY_READINESS_SCRIPT}" \
  --plan /tmp/plan.yaml \
  --pr-data /tmp/pr_data.json \
  --item <item-id>
```

rather than re-deriving the readiness rule in either skill — it reuses
`build_dashboard.py`'s own `Item.is_ready_to_unblock_dependents()`, so
neither skill can ever silently disagree with the dashboard about what
counts as ready. It prints one JSON list, one entry per `depends_on` entry,
in order: `[{"identifier": ..., "title": ..., "live_state": ...,
"is_ready": <bool>}, ...]`.

A dependency the script reports `"is_ready": false` for (still not-started,
only a draft pull request, or was ready and has since regressed to blocked
or closed unmerged) is a real, common cause of a stall — flag it explicitly
in the proposed plan's assumptions rather than quietly proceeding as if it
were ready. See `plans/README.md` for why an open, non-draft pull request
already counts as ready even though it hasn't merged yet — this repo's
normal workflow stacks new work on it before it does.
