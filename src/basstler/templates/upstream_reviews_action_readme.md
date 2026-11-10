# basstler upstream reviews

Kept by basstler's `/upstream-reviews` skill. Each read pushes a branch of its own under
`{{ requests }}/`, starting from this one, with a `{{ request }}`. That push runs
`{{ workflow }}`, which reads the upstream as the request asks and commits `{{ result }}`
onto the same branch; the session reads it and deletes the branch. Each run also
deletes request branches left for over an hour by a read that gave up. Nothing here is ever
merged anywhere.

Install or update it with `/setup-personal-notes`, which runs
`python -m basstler.setup.steps install-upstream-reviews-action`.
