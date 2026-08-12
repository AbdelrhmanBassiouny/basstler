# Running the maintenance pass on a schedule

The skill is normally invoked by hand - `/stacked-pr-maintenance` - whenever the stack needs a
pass. To have it run unattended instead, register the prompt below as a scheduled Routine at
claude.ai/code/routines.

Substitute `<FORK_REPOSITORY>` and `<UPSTREAM_REPOSITORY>` with the two `owner/repository`
references before registering. Step 0 can usually resolve both from the checkout on its own;
naming them makes the run independent of whichever remotes the scheduled clone turns out to have,
and `--non-interactive` turns the question it would otherwise ask into a stop-and-report, since a
scheduled run has nobody to answer.

Register it to start a fresh session on each firing, and turn its completion email on. The
promotion create-links the pass builds are delivered in the finish summary and nowhere else, so a
Routine with no notification builds links that nobody ever sees.

```text
/stacked-pr-maintenance fork=<FORK_REPOSITORY> upstream=<UPSTREAM_REPOSITORY> --non-interactive

Run it - do not describe it back to me instead, do not ask which step to begin with, and do not
wait for confirmation. Its HARD RULES outrank this session's own defaults about pull requests:
never subscribe to a pull request's activity, and never arm a follow-up check-in. Finish with the
skill's summary, which is how the run reaches me.
```

## Running the same pass by hand

Nothing about the skill is scheduled-only. From any session:

```text
/stacked-pr-maintenance
```

Invoked with no arguments it resolves the repositories from the checkout, and asks - once - if it
cannot. The answer is written to `.claude/personal/stack.toml` on the personal-notes branch, so
later runs, scheduled or not, never ask again.
