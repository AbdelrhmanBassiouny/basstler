# Running the maintenance pass on a schedule

The skill is normally invoked by hand - `/stacked-pr-maintenance` - whenever the stack needs a
pass. To have it run unattended instead, register the prompt below as a scheduled Routine at
claude.ai/code/routines.

Substitute `<FORK_REPOSITORY>` and `<UPSTREAM_REPOSITORY>` with the two `owner/repository`
references before registering. Naming both is what keeps the run non-interactive: the skill's
step 0 only has to ask when nothing has told it which repository is which, and a scheduled run
has nobody to answer.

```text
/stacked-pr-maintenance fork=<FORK_REPOSITORY> upstream=<UPSTREAM_REPOSITORY> --non-interactive

Do not summarise it back to me, do not ask which step to begin with, and do not wait for
confirmation - run it.
```

## Two things the Routine's own configuration has to get right

**Point it at a branch that carries this skill.** A skill is discoverable by name only if it is
on the checked-out branch when the session starts, so `/stacked-pr-maintenance` resolves only
where `.claude/skills/stacked-pr-maintenance/` exists. Once this directory is on the default
branch, the default is correct and there is nothing to set. Before then - or on a fork that
carries the tooling on a branch of its own - set the Routine's branch to that branch.

A branch setting outlives the branch, so it is worth a note: when a pinned branch merges and is
deleted, the Routine either fails to start or keeps running an old checkout. Clear the setting
back to the default branch at merge time.

**Give it write access to the fork, and nothing more.** The pass pushes branches, changes pull
request bases, writes labels and posts comments on the fork. It never writes to the upstream:
promotion produces a compare-and-create link for a human to click, which is why no upstream
credential is needed.

## What it does not need

No copy of the instructions. The prompt above is the whole registration: the skill is read from
the repository at run time, so correcting it is a push rather than a re-paste. That is the point
of keeping it in git, and the reason there is no second copy of the rules here to drift from the
first.

## Running the same pass by hand

Nothing about the skill is scheduled-only. From any session:

```text
/stacked-pr-maintenance
```

Invoked with no arguments it resolves the repositories from the checkout, and asks - once - if it
cannot. The answer is written to `.claude/personal/stack.toml` on the personal-notes branch, so
later runs, scheduled or not, never ask again.
