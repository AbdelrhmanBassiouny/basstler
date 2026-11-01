# A worked example: idea to plan page

A short, concrete walkthrough of the plan system end to end, using
a small **fictional** example plan — no real branches, PRs, or GitHub calls
involved.

The only thing this assumes is a fork of this repository with the `.claude/`
tooling on its default branch. If you haven't set anything up yet, run
`/setup-personal-notes` once — it checks what's already in place, asks about
anything it can't decide for you, and finishes in seconds if you're already
set up. (You don't have to run it first: any skill below runs it for you if
you need it, without asking whether to.) [`hooks/README.md`](../../hooks/README.md) documents what it
configures, for when you want the details.

The example data referenced below is committed alongside this file, under
[`example/`](./example/) — real `plan.yaml`, `roadmap.md`, and `pr_data.json`
files, not just prose.

## 1. Start with the idea, in plan mode

You describe what you want, in your own words. No special syntax:

> **You:** Notification delivery fails hard on the first transient error. I
> want to add a retry mechanism with backoff, a circuit breaker so a
> persistently failing downstream service doesn't get hammered, and the
> metrics/alerting to run it safely. Can you plan this out?

Claude enters plan mode, asks any clarifying questions, and proposes a
concrete plan — phases, files, how each part gets verified. You review it and
approve.

## 2. Turn the approved plan into a tracked, multi-PR plan

A single Claude Code plan-mode plan is ephemeral — it lives in this one
conversation. Once it's clear the work spans more than one PR or session (as
this one does: backoff, circuit breaker, dead-letter queue, and retry
metrics are each their own branch), turn it into a **persistent plan**:

> **You:** `/plan-create notification-retry-overhaul`

The [`plan-create`](../plan-create/SKILL.md) skill asks where the plan's
content comes from — here, "from this conversation" (the plan you just
approved). It then asks a few structural questions it won't guess at (does
this need multiple tracks? waves?), drafts a schema-conformant
`plan.yaml`/`roadmap.md`, validates it, and — after asking whether you want
one — optionally creates a **tracking issue** as a shared mailbox for later
structural changes (skipped in this example, since it's small enough for one
session to own end to end). Finally it pushes both files to the
`claude/personal-notes` branch; that push builds the plan's page on the plan site.

## 3. The resulting plan.yaml and roadmap.md

Here's what came out the other end (the real files are at
[`example/plan.yaml`](./example/plan.yaml) and
[`example/roadmap.md`](./example/roadmap.md)):

```yaml
schema_version: 1
id: notification-retry-overhaul
title: Notification Retry Overhaul
default_repository: example-org/notification-service

waves:
  - id: wave-1
    name: "Wave 1: Retry foundations"

tracks:
  - id: retry-logic
    name: Retry logic
    wave: wave-1
  - id: observability
    name: Observability
    wave: wave-1

items:
  - id: retry-backoff-strategy
    title: Exponential backoff strategy for retries
    branch: retry-backoff-strategy
    track: retry-logic
    status: done
    pull_request_number: 101

  - id: retry-circuit-breaker
    title: Circuit breaker around the retry loop
    branch: retry-circuit-breaker
    track: retry-logic
    status: in progress
    pull_request_number: 102
    depends_on: [retry-backoff-strategy]

  # ...three more items - see example/plan.yaml for the full list
```

`plan.yaml` is the **thin, structured** half: waves/tracks/items, statuses,
dependencies, PR numbers, and each item's scope in its `notes`. The plan's
standing rules - the decisions every item must follow - go in `roadmap.md`,
as a title and a short list of entries:

```markdown
# Notification Retry Overhaul — standing rules

- Retries use exponential backoff with jitter, not a fixed delay.
- Every item in the retry-logic track stacks its branch directly on
  retry-backoff-strategy's branch once that pull request is ready for review.
```

History and finished work are kept in neither file; they live in git and on
the pull requests.
Neither file ever stores live GitHub state (open/draft/merged/CI) — that's
always fetched fresh, every time the plan site is built.

## 4. Open the plan's page

Every push to the notes branch rebuilds the plan site, so the plan's page is
already there — `plan_site_page_url notification-retry-overhaul` prints its
address. The build cross-checks every item's PR against live GitHub state:

![The plan page — status counts, the next steps, and a column per wave with a card per item](./example/screenshots/plan-page-overview.png)

A few things worth noticing in this one small example:

- **Status counts and a drift flag** — `retry-fallback-queue` is marked `done`
  in the manifest, but its pull request (`#103`) is still open. That's the one
  thing a manifest can get wrong that GitHub itself can settle: the "Fix the
  manifest" list names exactly which item and why.
- **"Ready to start"** — `retry-metrics` hasn't started yet, but its one
  dependency (`retry-backoff-strategy`) is done, so it's safe to build on.
- **"Blocker may be cleared"** — `retry-load-testing` is blocked (on load-test
  cluster capacity, per its own `blockers` note), but its dependency is now
  ready too, so it's worth a look.
- **"Ready to review"** — `retry-config-flag` has an open, still-draft pull
  request with nothing blocking it from being reviewed right now, and
  `retry-circuit-breaker` joins it because its one dependency
  (`retry-backoff-strategy`) has already merged. A dependency only holds its
  dependent out of this list while it has no pull request at all — once one
  exists, whether it is a draft, ready, or already landed, the branch stacked
  on top is worth reviewing.
- **Done items are hidden by default** — the "Show done items" checkbox
  reveals `retry-backoff-strategy` and `retry-fallback-queue` when you want
  them back.

The other drift with no judgment call in it — a merged pull request whose item
is still marked anything but `done` — is corrected in the manifest itself:

> **You:** `/plan-sync notification-retry-overhaul`

The [`plan-sync`](../plan-sync/SKILL.md) skill marks every such item `done` and
pushes the correction, which rebuilds the page.

## 5. Kick off, resolve, or review a specific item

Every not-done item's card has an action button, worded to match its status,
plus a model dropdown next to it:

![An item's "Resume" button with its model dropdown open](./example/screenshots/plan-page-action-buttons.png)

Clicking a button **copies the command** to your clipboard (a web page
can't start a session itself) — paste it into a fresh session to run it. If
you pick a model from the dropdown first, a `/model MODEL_ID` line is
prepended so the pasted session starts on that model.

- **Kick off a not-started item** — `retry-metrics`'s "Start now"
  button copies `/plan-item-kickoff notification-retry-overhaul
  retry-metrics`. The [`plan-item-kickoff`](../plan-item-kickoff/SKILL.md)
  skill gathers the item's context (manifest entry, roadmap history, its
  dependency's live state, patterns from the merged pull requests that last
  changed the files it will touch) and
  proposes a concrete implementation plan via plan mode — it never writes
  code itself.
- **Resolve a stalled item** — `retry-load-testing`'s "Resolve" button copies
  `/plan-item-resolve notification-retry-overhaul retry-load-testing`. The
  [`plan-item-resolve`](../plan-item-resolve/SKILL.md) skill is
  `plan-item-kickoff`'s counterpart for an item that already has real state:
  it gathers PR mergeable status, CI, review comments, and recorded
  blockers, then proposes a plan to resolve whatever's actually stalling it
  — same plan-mode-only contract, no code changes.
- **Review a stalled draft PR** — `retry-circuit-breaker` and
  `retry-config-flag` both have open, still-draft pull requests. Their pull
  request chips link straight to the PRs on GitHub.

## Where to go from here

- [`hooks/README.md`](../../hooks/README.md) — the setup guide: what
  `/setup-personal-notes` configures, and how to change any of it.
- [`plan-schema.md`](./plan-schema.md) — the full `plan.yaml` schema
  reference.
- [`plan-create/SKILL.md`](./SKILL.md),
  [`plan-sync/SKILL.md`](../plan-sync/SKILL.md),
  [`plan-item-kickoff/SKILL.md`](../plan-item-kickoff/SKILL.md),
  [`plan-item-resolve/SKILL.md`](../plan-item-resolve/SKILL.md) — the exact
  mechanics behind each step above.
