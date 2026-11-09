# Pull-request rules

These hold while a skill that links this document runs, for the pull requests it opens,
pushes to or answers reviews on; where the skill says otherwise, the skill holds. Outside
such a skill, the session's own instructions decide.

## Pull requests

- Always open pull requests as **drafts**. Never open a PR as ready-for-review
  by default; mark it ready only when explicitly told to.
- Always convert a PR back to **draft** after pushing any commit to it or
  otherwise modifying it, even if it was previously marked ready for review.
  Mark it ready again only when explicitly told to.
- Bug-fix PRs must always carry the **`bug`** label.
- Keep bug-fix PRs focused: one root cause per PR, based off the default
  branch, no unrelated cleanup bundled in.
- Always include a link to the session that created the PR in the PR
  description.
- Keep the PR description up to date: after pushing any change that alters
  what the PR does, update the description to match. Never leave it
  describing an earlier state of the PR.
- Never subscribe to a pull request's activity, and never offer to watch,
  monitor, babysit or autofix one. Opening a PR ends the session's obligation
  to it: push it, report in the chat what you did and what is still
  outstanding, and stop. A CI failure or a review comment is handled when
  the user asks for it.

## Review comments

- Resolve a review comment thread only once you have genuinely done what it
  asked. If instead you need to ask what to do, or you are not taking an
  action, do not resolve it — reply explaining the situation and asking the
  question.
- Always reply to a PR comment explaining what you did before resolving it.
