# Publishing the plan site without `PLAN_SITE_TOKEN`, or with less work

Analysis for the `token-free-site` item of the `basstler-setup-ux` plan. Nothing here
changes production. It covers:
- how the site is published today;
- the token-free options;
- how to make the token fast path easier and more reliable;
- whether all plans could live in one hub, before and after basstler v3.

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

### What the token costs, measured on 2026-11-05

The last 100 dispatch runs of each notes repository:

| Notes repository | Runs since | success | failure | cancelled |
|---|---|---|---|---|
| `AbdelrhmanBassiouny/basstler` | 2026-11-01 | 90 | 0 | 9 |
| `AbdelrhmanBassiouny/cognitive_robot_abstract_machine` | 2026-11-02 | 29 | 62 | 9 |

The job logs of the cram failures show two causes:
- **61 runs:** the secret was not stored. `GH_TOKEN` is empty and `gh` asks for a
  token. This lasted two days, from 2026-11-02 to 2026-11-04, and every notes push in
  that time left the site stale. No run said what was missing.
- **1 run:** `gh workflow run` got a 502, which the `retry-dispatch-step` item covers.

Since 2026-11-04 09:45, all 31 finished runs succeeded.

So the token is not unreliable once it is stored. Getting it stored is the problem.

## Constraint: no workflow runs on a schedule

The `actions-budget` plan has a standing rule that no workflow has a `schedule`. It
was adopted after GitHub disabled Actions on the cram fork for wasted compute.
`basstler.actions_budget` reports a scheduled workflow as `ScheduledWorkflow`, and
`basstler-v3-plans`' roadmap repeats the rule for every new workflow.

That rules out options A and B below, and their prototype, unless the user makes an
exception for the site repository. They are kept for the record, and the
recommendation no longer rests on them.

### Recommendation: no exception

Keep the rule; F makes a schedule unnecessary.
- **Reliability:** GitHub delays scheduled runs under load and may drop them, most
  often near the start of an hour. It disables a scheduled workflow after 60 days
  without repository activity. A poll gives neither a fixed delay nor a guaranteed run.
- **Determinism and freshness:** a poll's delay depends on when the tick falls, and
  between ticks the site is stale. A push that starts the build has neither problem.
- **Actions budget:** a job is billed by the started minute, so a 5-minute poll costs
  at least 288 minutes a day, about 8,600 a month. That is free on a public site
  repository, but it is the kind of idle compute that got Actions disabled on the
  cram fork. On a private one it is over four times the free plan's 2,000 minutes.
- **If ever needed:**
  - only on the site repository;
  - change-gated as in B, with a 2-minute timeout and one concurrency group;
  - no more often than every 15 minutes;
  - declared in `basstler.actions_budget` as the one allowed schedule, so the check
    still fails on any other.

## Token-free options

### A. Scheduled build on the site repository (breaks the no-schedule rule)

stack-board runs the full build on `schedule`, as its legacy board did until
2026-11-01 (every 15 minutes).
- **Gained:** no token.
- **Latency:** at least 5 minutes, plus GitHub's scheduling delay.
- **Actions usage:** a full build on every tick, whether or not anything changed.

### B. Change-gated poll on the site repository (breaks the no-schedule rule)

Like A, but each tick first runs a job of a few seconds. That job lists, with `git
ls-remote` and no credential:
- the hub's repository list;
- each listed repository's notes branch head;
- each listed repository's default branch head.

The build runs only when one of them moved. It covers the same events as today's two
dispatch workflows and costs one short job per tick. The detection was verified
locally against the live repositories. A keep-alive would be needed, because GitHub
disables a scheduled workflow after 60 days without repository activity.

### C. Webhook relay, D. GitHub App

GitHub cannot deliver a webhook to a workflow, so C needs a server that holds a token.
D needs the App's key stored as a secret, or a server. Both move the credential
instead of removing it, and both add infrastructure someone has to host.

### E. Each notes repository publishes its own Pages

This is instant and token-free. It loses the single site and the hub, and takes the
repository's one Pages slot, which a project may already use for its docs.

### F. The writer starts the build

basstler's own commands (`save-plan.sh`, `plan.item_bootstrap`, `save-pr-progress.sh`)
already push the notes. After the push, they could start `plan-site.yml` themselves,
with the credential they pushed with:
- **Local sessions:** the user's `gh` login.
- **Cloud sessions:** the site repository attached with push access.

What it covers and costs:
- **Coverage:** every plan save, which is most of the triggers, with no stored secret
  and no schedule. Merges are not covered. They stay with the merge workflow, or with
  `page-merge-recheck`, the planned browser re-check of merges. #115 chose the merge
  workflow over a browser merge re-check, so dropping the workflow reopens that
  decision.
- **Cost:** a cloud session needs one more attachment. The `fewer-questions` item
  would have to name that attachment up front. A save whose build fails to start must
  report it rather than pass silently.

#### Prototype of F, on this branch

- `basstler.plan_site.build_start` reads the site repository's default branch and
  dispatches `plan-site.yml` on it through the REST API, with the session's credential.
  It prints whether the build started. When it did not, it says what to do:
  - in a cloud session, attach the site repository with `add_repo` and push access, and
    if that is refused, ask the user, with attaching as the recommended answer;
  - elsewhere, log `gh` in with access to the site repository.
- `save-plan.sh` runs it after every saved plan. All plan writes go through that script,
  `plan.item_bootstrap` included. A failure to start never fails the save, because the
  notes are already pushed.
- The session rules tell every cloud session the same, so the request reaches the user
  however the save was run.

Verified on 2026-11-05 from a cloud session with stack-board attached for push: the
command started stack-board's build. Without the attachment the session proxy refuses
the site repository, and that refusal is what the command reports. `gh workflow run`
without `--ref` fails in a cloud session because it looks up the default branch with
GraphQL, which the proxy refuses. The prototype therefore uses REST only.

Still on the notes token:
- **Merges:** the merge workflow still needs it.
- **Edits outside basstler:** a hand-edited notes branch still needs it.

## Making the token fast path easy and reliable

What the user does today is set out in `basstler.plan_site.user_steps`:
- **Create the token:** five browser steps.
- **Store it:** one `gh secret set` line per notes repository. Its loop splits the
  repositories on commas, which is the `fix-secret-loop` item.
- **Merge** the merge workflow.

Proposals, most effect first:

1. **Fail loudly on a missing secret.** The dispatch step checks `GH_TOKEN` is not empty
   and stops with an error that names `PLAN_SITE_TOKEN` and the repository, and gives
   the store command. This removes the silent two days above. The session-start
   `plan_site` row can repeat the same line.
2. **One command that stores and proves the token.** It takes the token from standard
   input once, stores it in every registered repository, then starts each dispatch
   workflow and waits for its run. It ends with *done* or with the failing run's error
   line. This combines `fix-secret-loop` and `trigger-and-done`. Storing a secret needs
   the user's own `gh` login, because a cloud session's credential is refused, so the
   command runs on the user's machine.
3. **Pre-filled token page.** GitHub fills the fine-grained token form from the query
   string of `settings/personal-access-tokens/new`, with `name`, `description`,
   `target_name` (the owner), `expires_in` and one parameter per permission, such as
   `actions=write`. This replaces four of the five browser steps with a link. The
   repository selection stays manual: no documented parameter selects repositories.
   *To verify on github.com.*
4. **Least privilege.** Starting the build needs Actions write on the site repository
   only. The steps asked for Contents read on every registered repository as well.
   Nothing uses that: the token's one use is `gh workflow run` on the site repository,
   and the build reads the notes with the site repository's own `github.token`. The
   request dates from the first version of publishing, `eca4d650`.
   *Done on this branch:* the steps now ask for Actions write on the site repository
   alone. The token then never changes when a repository joins the site. Only the
   store step repeats, for the new repository.
5. **Organisation-owned notes repositories** can store the token once, as an
   organisation secret shared with the selected repositories. Repositories owned by a
   user account have no shared Actions secrets, so they keep one secret each.
6. **Expiry.** A fine-grained token expires. The dispatch's error line for a refused
   token can give the pre-filled link and the store command, so renewing takes the
   same two steps as setting it up.

## All plans in one hub repository

The idea: store every plan in the site repository instead of each repository's notes.
A push there starts the build through the site repository's own `push` event, at once
and with no token.

Against it, today:
- **The user's rule:** plans for one repository live in that repository, and #138
  enforces that when a plan is saved. A hub reverses this.
- **Write access:** every session that saves a plan needs write access to the hub. In
  a cloud session that is the same extra attachment as option F, so for plan saves a
  hub gains nothing over F.
- **Split state:** personal notes and PR progress stay per repository, so the state
  would be split across repositories.
- **Merges:** they still happen in the work repositories, so they still need the merge
  workflow or the browser re-check.

### In basstler v3

`basstler-v3-plans` moves plans from `plan.yaml` on the notes branch to a tracking issue
with sub-issues, and the site reads them (`plan-site-from-issues`). The notes stop being
the plan store, so "plans in the hub's notes" has no v3 form. The v3 question is where
the plan issues live:

- **Issues in each repository.** This matches the per-repository rule. The build is then
  started by issue events in each repository, and starting a workflow in the site
  repository from them needs a cross-repository credential. The token problem moves
  from notes pushes to issue events, unless the writer starts the build (F).
- **Issues in a hub repository.** Issue events in the site repository start the build
  with no token and at once. Pull requests in other repositories still close their
  items with `Fixes owner/repo#n`. This is the `team-repository` plan's design: a team
  repository holds the shared plans, with one issue per item.

Recommendation: do not move today's plans to a hub. v3 replaces the notes store anyway,
and the move would reverse #138.

For v3, keep plan issues in each repository:
- **Focus:** someone working on one repository sees only its plans in its issue list,
  search and notifications. GitHub's own filters cover the rest: labels, milestones,
  closing as *not planned*, pinning.
- **Team-ready:** each repository's issues follow its own access, so a team works on
  its repository's plans without access to a shared hub.
- **One view across repositories:** the plan site already joins every repository's
  plans.

Freshness then comes from two places:
- **Edits made by a session:** the session starts the build (F), with no token.
- **Edits made on github.com** (a comment, a closed or relabelled issue): each
  repository needs an `issues` and `issue_comment` workflow that starts the build. It
  uses the same least-privilege token, Actions write on the site repository only, and
  fails loudly when the token is missing (proposal 1).

The plan page can also read an issue's live state in the browser, as it already does
for pull request states. A page is then fresh even before its rebuild.

## Recommendation, for discussion

1. **Now, small:** make the fast path reliable and quick to set up, with proposals 1–4
   above. Most of this is in already planned items (`fix-secret-loop`,
   `trigger-and-done`, `retry-dispatch-step`). Proposals 1, 3 and 4 are new.
2. **F, prototyped on this branch:** basstler's own plan saves start the build. Plan
   saves no longer need the token; the merge workflow still does.
3. **v3:** plan issues per repository, with F for session edits and an issue-event
   workflow for edits made on github.com, using the least-privilege token.

No schedule: the no-schedule rule stays, with no exception.

## Prototype of B

[`plan-site-poll-prototype.yml`](plan-site-poll-prototype.yml) is B's change gate alone.
It never builds or deploys. Each tick it computes the fingerprint and, when it changed,
logs the heads and the delay since the newest commit. It remembers fingerprints in the
Actions cache.

It runs on a schedule, so it breaks the no-schedule rule. It would go on stack-board's
default branch only if the user grants the exception, and would be removed after a day
of measurements.
