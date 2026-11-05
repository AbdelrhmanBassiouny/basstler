# Publishing the plan site without `PLAN_SITE_TOKEN`

Analysis for the `token-free-site` item of the `basstler-setup-ux` plan. Nothing here
changes production. It describes how the site is published today, the token-free
options, how they compare, and a prototype to measure the recommended one on
stack-board.

## How the site is published today

- **The build** runs on the site repository (stack-board). `plan-site.yml` calls
  basstler's reusable `plan-site-build.yml`, which reads the hub file on the registry's
  notes branch and fetches every listed repository's notes. It reads the pull request
  states with stack-board's own `github.token`. It deploys only when `site-digest.txt`
  changed.
- **The trigger** sits on every notes repository: `plan-site-dispatch.yml` runs on each
  push to the notes branch, and `plan-site-merge.yml` runs on each merged pull request
  (`pull_request_target`). Both run `gh workflow run plan-site.yml --repo <site>`.
- **`PLAN_SITE_TOKEN` exists only for that trigger.** A workflow's `GITHUB_TOKEN`
  cannot start a workflow in another repository, so each notes repository stores a
  fine-grained token with Actions write access to the site repository. The build needs
  no user token.

What the token costs, measured on 2026-11-05 over the last 100 dispatch runs of each
notes repository:

| Notes repository | Runs since | success | failure | cancelled |
|---|---|---|---|---|
| `AbdelrhmanBassiouny/basstler` | 2026-11-01 | 90 | 0 | 9 |
| `AbdelrhmanBassiouny/cognitive_robot_abstract_machine` | 2026-11-02 | 29 | 62 | 9 |

Each failed run is a notes push that left the site stale. Setup also has to make the
user create the token, grant it every published repository, store it in each one and
renew it when it expires. That is most of the user-only steps
`basstler.plan_site.publication` prints.

## Options

### A. Scheduled build on the site repository

stack-board runs the full build on `schedule`, as its legacy board did until
2026-11-01 (every 15 minutes).

- **Token**: none. Only stack-board's own `github.token`.
- **Latency**: the schedule interval plus GitHub's scheduling delay. The shortest interval
  is 5 minutes, and runs are delayed under load, most often at the top of the hour.
- **Actions usage**: a full build (Python, `pip install basstler`, every fetch, every
  pull request read) on each tick, whether or not anything changed. That is 288
  builds a day at 5 minutes. Free while stack-board is public, but each build also
  spends GitHub API requests on unchanged state.

### B. Change-gated poll on the site repository (recommended baseline)

Like A, but each tick first runs a job of a few seconds. It lists the heads that start
a build today, using `git ls-remote` with no credential:
- the hub file's repository list on the registry's notes branch;
- each listed repository's notes branch, which today starts the dispatch;
- each listed repository's default branch, where a merge moves it (today's merge dispatch).

The build job runs only when that fingerprint differs from the last one seen.

- **Token**: none.
- **Coverage**: the same events as today's two dispatch workflows. A pull request
  opened, closed without merge or changing CI state starts nothing today either. A
  periodic full build (for example hourly) can cover that if wanted.
- **Latency**: as A.
- **Actions usage**: one short job per tick plus a build per real change. That is the
  same number of builds as today, and fewer than today's dispatch runs, because a
  burst of pushes between two ticks becomes one build. Free on a public site repository.
  A private one would bill each tick as one minute, about 8,600 minutes a month at
  5 minutes, so the interval would have to grow.
- **Security**: removes the token from every notes repository and removes the
  `pull_request_target` merge workflow, the one workflow that reads a secret on a
  fork's pull request.

### C. Webhook

GitHub cannot deliver a repository webhook to a workflow. A relay service (a small
serverless function) would receive the push webhook and dispatch the build, holding a
token itself. This is token-free for the user only if basstler runs that service for
everyone. It adds infrastructure to operate and secure, and the token still exists,
moved to a server.

### D. GitHub App

An App's installation token can dispatch across repositories. Either the notes
repositories store the App's private key as a secret (a token by another name) or a
server mints installation tokens on webhooks (C again). Installing the App is
one step instead of a token, but someone has to own and host the App.

### E. Each notes repository publishes its own Pages

Each notes repository builds its plans with its own `GITHUB_TOKEN` and deploys to its
own Pages. This is instant and token-free, but loses the single site and hub. It also
takes the repository's one Pages slot, which a project may already use for its docs
(`cognitive_robot_abstract_machine` has documentation workflows).

## Private notes repositories

The build already fetches notes anonymously and reads pull requests with stack-board's
`github.token`, so a private notes repository is *not* published today, whatever the
trigger. A token-free trigger changes nothing for it. Supporting private repositories
needs a read credential in any design. A poll (B) needs it once, read-only, on the site
repository, instead of once per notes repository with write access, as the dispatch
does.

## Risks of a schedule

- **Inactivity**: GitHub disables a scheduled workflow in a public repository after 60
  days without repository activity, and stack-board gets no commits from publishing. A
  keep-alive is needed: the workflow re-enabling itself through the API with
  `actions: write` on its own repository, or a periodic commit. The prototype measures
  latency only. The keep-alive must be settled before production.
- **Delays**: scheduled runs can be skipped or delayed under load. The prototype logs the
  delay of each detected change, so this is measured, not assumed.

## Recommendation, for discussion

Make B the default and keep the dispatch as an optional fast path:

1. The site workflow polls with the change gate and gets a keep-alive.
2. `PLAN_SITE_TOKEN` becomes optional. A repository that stores it still starts the build
   at once, and one that does not is picked up by the next tick. The dispatch step must
   then skip, not fail, without the secret (the `fix-secret-loop` item's concern).
3. Setup drops the token steps from the required path and offers them as "instant
   updates".

Open for the user to decide:
- Is a delay of 5 minutes or more acceptable as the default?
- Should the merge workflow go even for users who keep the token?
- Should private notes repositories be in scope now?

## Prototype

[`plan-site-poll-prototype.yml`](plan-site-poll-prototype.yml) is the change gate of B
alone. It never builds or deploys. Each tick it computes the fingerprint and, on a
change, logs which heads moved and how long after the newest commit the tick saw it.
It remembers fingerprints in the Actions cache.

To verify it, copy it to `.github/workflows/` on stack-board's default branch (schedules
run only there) and leave it for a day. Then compare its detections with the dispatch
runs of the same period:
- every notes push or merge is detected;
- the delay distribution;
- the number of ticks and their duration.

Remove it afterwards.
