## PR progress: plan-saves-start-site-build (#139)

Plan
- Settle where the unified attempt/reaction pattern (thread on build_start.py:133) is
  tracked; that thread stays open until then.

Done
- 68e0a841: logger, EnvironmentFlag.TRUE + is_true (3 readers), Repository.workflow_dispatch_path,
  one GitHubAttemptClient, gh auth login command, tests for the refusal report and the local
  session; full suite 2129 passed at 68e0a841. 11 of 12 threads replied and resolved.
- Merged into #140's branch (6dfdfc5d) by hand: maintenance restack needs an upstream.

Next
- Read CI on 68e0a841. #140's token_storage.py:215 still builds the dispatch path by hand
  and prints with print().
