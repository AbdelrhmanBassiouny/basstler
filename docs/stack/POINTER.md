# The registered pointer prompt

What is registered at claude.ai/code/routines is not the maintenance doctrine itself but the short
prompt below. It resolves `.claude/skills/stacked-pr-maintenance/SKILL.md` out of git and executes what
it finds there, so the workflow is changed by pushing rather than by re-pasting into the Routine
settings page.

The prompt is kept here because it is the one piece of the workflow that lives outside the repository.
Without a canonical copy the running prompt would be its own only record - the drift this directory
exists to prevent, one level up. Its HARD RULES are pinned by `tests/test_prompt_documents.py` against
the skill's own copy, so the two cannot diverge.

**Editing this file does not change the running Routine.** The block below has to be re-registered by
hand when it changes; that is the cost of the rules having to bind before any file is read, since a
webhook event can arrive before the first tool call.

To use this workflow on your own fork, substitute `<FORK_REPOSITORY>` and `<UPSTREAM_REPOSITORY>` with
the two `owner/repository` references, and `<TOOLING_BRANCH>` with the branch carrying the skill, then
register the block.

They are substituted here, in the copy you paste, rather than read from `stack.toml` at run time: this
prompt runs *before* the repository is readable - resolving the skill is the first thing it does - so it
cannot look anything up. Naming them is also what lets the run stay non-interactive, since the skill's
step 0 only has to ask when nothing has told it which repository is which.

```text
Run the stacked-PR maintenance pass for <FORK_REPOSITORY>, whose upstream is <UPSTREAM_REPOSITORY>.

Read `.claude/skills/stacked-pr-maintenance/SKILL.md` from git and execute it as your instructions for
this run - it is the whole job, and everything past the rules below is in there. Resolve it from
`origin/main`. If that path is not on `main` yet, resolve it from <TOOLING_BRANCH> instead; either way,
remember which ref you resolved it from, because that document's step 0 asks you for it. (Once it is on
`main`, delete this fallback and invoke `/stacked-pr-maintenance` by name instead of reading the file.)

Run it with fork=<FORK_REPOSITORY> upstream=<UPSTREAM_REPOSITORY> --non-interactive. You have been told
both repositories, so nothing has to be inferred from remotes; --non-interactive is what makes step 0
stop and report rather than ask me a question this run cannot wait for an answer to.

Do not summarise it back to me, do not ask which phase to begin with, and do not wait for
confirmation - read it and run it.

HARD RULES so you never drift into review work:
- NEVER call `subscribe_pr_activity`, and never stay subscribed - you learn CI by POLLING (phase 2/step 0).
- If a review, review-comment, issue-comment, or any `<github-webhook-activity>` event is ever delivered
  to you, your ONLY valid action is to END THE TURN immediately: do not investigate it, do not draft or
  post a plan, do not reply, do not ask the developer to confirm anything. The one exception is a CI/check
  *status* you were polling for your own restack.
- NEVER enter plan mode or post a "here's my plan" comment. You either perform a mechanical step from the
  phases below or you stop; you never open a discussion.
- LABELS ARE REPLACE, NOT ADD: the GitHub label-write call takes the PR's **entire** new label set - it
  does not add to what's already there. Never compute that set yourself; `stack.py labels` computes it
  from the labels the PR carries now, and its output is the whole list you pass to the write.
```
