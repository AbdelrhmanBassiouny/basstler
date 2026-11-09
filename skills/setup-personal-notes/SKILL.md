---
name: setup-personal-notes
description: One-time setup of the personal-notes branch, its configuration and the package's dependencies. Invoke as "/setup-personal-notes". Use on first setup, or when personal notes, PR progress or plans are not working.
allowed-tools: Bash, Read, Write, AskUserQuestion, mcp__github__get_me, mcp__github__get_label, mcp__github__actions_list, mcp__github__get_job_logs
---

# Set up personal notes

Run commands as [`running-commands.md`](../running-commands.md) says, with
`${CLAUDE_PLUGIN_ROOT}` as the `${BASSTLER_PLUGIN_ROOT}` it and every linked document name.

Gets a clone from "I have a fork of this repo and nothing else" to "personal
notes, PR progress and plans all work," asking one question per
decision that is genuinely the user's, with a default they can accept as-is.

**Fast path first.** Every step below is conditional on
[`check-setup.sh`](../../hooks/check-setup.sh) reporting that specific thing
missing. If it reports nothing missing, check only the labels the script can't
see (step 5's last part) and stop there. A re-run on an already-set-up clone
must be a near-no-op, not an interrogation.

**A denied command is a question, not a dead end.** If the permission system
denies a command this skill runs (the dependency install, for one), follow
[`session-rules.md`](../../hooks/session-rules.md): ask the user to accept it at
once, and run it when they do. That file is loaded into every session, so the
rule binds every skill, not only this one.

**Never guess a value that is the user's to choose.** Where their notes live
and what goes in them are personal; ask, with a default. Everything else
(installing a documented dependency, running a read-only script) is mechanical
— just do it.

## 1. Find out what is actually missing

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/check-setup.sh" $ARGUMENTS || true
```

`$ARGUMENTS` is whatever this skill was invoked with: `--require-upstream`
when a skill needing the stacked-PR workflow's upstream ran it, nothing
otherwise. Pass the same to every run of the check below.

The script prints one tab-separated `<check>` / `<status>` / `<detail>` row per
check and exits non-zero if any row is `needs-setup`, `in-progress`,
`unverified` or `mismatched` (`|| true` above keeps a non-zero exit from ending the block early
— the rows are the point, not the status). Read its own header comment for
what each check means.

On the first run of a session, `package_dependencies` can be `in-progress` and
`claude_local_md` `needs-setup` only because the session start is still
installing the package. Tell the user so, wait as the `in-progress` paragraph
below says, and run the check once more before reading either row as a fault.

**If it exited 0:** no row is `needs-setup`, `in-progress`, `unverified` or
`mismatched`.
List what was found (the remote, branch and path in play, that dependencies
and `CLAUDE.local.md` are in place, and the `basstler_version` row), then check
the labels as step 5 describes. If the `plan_site` row is `ok`, tell the user
everything is set up and stop. Otherwise the plan site is not publishing: say
so, run step 8, and never call the clone fully set up. Do not ask anything
else. Do not re-verify by hand what the script just verified.

**A `mismatched` row** means the plugin's hooks and the package they call are
not one release, so a hook can pass an option the package does not accept. Tell
the user, and follow the row's own detail to bring them together.

**An `in-progress` row** means a session start is installing that part right
now. Never install it yourself, and never run a `pip` command for it: wait with
`source "${CLAUDE_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh" && wait_for_basstler_install`
in one call, then run the check again.

**An `unverified` row** means nothing the script could read decides it yet, as
when GitHub refuses the session's `GH_TOKEN`; its detail says why. It is never a
pass. When the `plan_site` detail says `PLAN_SITE_TOKEN` was set after the
latest dispatch run, no run has used that token yet: tell the user the next push
to the notes branch settles it, and carry on with step 8 without reading that
run's log as the cause. Otherwise, for `plan_site`, read the same facts with the session's GitHub tools:
`mcp__github__actions_list` (`list_workflow_runs` on the notes repository's
`plan-site-dispatch.yml`, notes branch), then `mcp__github__get_job_logs` on the
latest failed run. Report how many runs failed, the latest run's conclusion and
address, and the failing step's error line, then carry on with step 8. When
those tools cannot read them either, report the row as *not verified*, never as
set up.

**Otherwise:** work through the `needs-setup` rows in the order printed —
they're ordered so an earlier fix can be a prerequisite of a later one — using
the steps below. Skip the step for any check already `ok`.

## 2. `tooling_files` / `session_start_hook` — the plugin is incomplete

Not fixable from here: the basstler plugin's own files are missing. Tell them to
reinstall the plugin (claude.ai Customize > Plugins, or `/plugin` in a local
session) and re-run. Stop; every later step depends on those files.

## 3. `claude_local_md_ignored` — CLAUDE.local.md could be committed

The project's `.gitignore` does not ignore `CLAUDE.local.md`, so the notes
could end up in a commit. Offer to add `CLAUDE.local.md` and
`.claude/settings.local.json` to it; ask before changing the tracked file.

## 4. Ask what only the user can answer

Steps 4 and 5 cover the `notes_branch`, `notes_file`, `git_identity`,
`package_dependencies` and `claude_local_md` rows, and the pull request
labels `check-setup.sh` cannot see. Everything mechanical about them is one
command that needs no session. This step only collects its arguments; ask
each question only when its row is `needs-setup`.

- **Where the notes live** (`notes_branch`). Is the notes remote the user's
  own fork, or a shared upstream they can't push to? A git remote URL doesn't
  say who owns it. Read the `notes_remote_url` row and get the user's GitHub
  login with `mcp__github__get_me`. If the URL's owner is that login, that
  remote is the answer. Otherwise ask where their notes should live, offering
  `https://github.com/<their-login>/<repo>` as the default, and note that a
  remote name already in the clone works too.
- **Starter notes** (`notes_file`). Offer to seed the new notes from
  [`starter-notes.md`](./starter-notes.md): conventions for pull requests,
  review comments and progress tracking, which they own and can edit. Default
  to yes. An empty file is fine too.
- **Their git identity** (`git_identity`). Ask for the name and email their
  commits should carry. Never take them from this clone's git config, which
  in a fresh session is the agent's own identity.

Then tell them plainly that **the remote choice does not survive a fresh
clone** (Claude Code on the web, any cloud environment). The command records
it in this clone's git config, and that config is gone next session. For
those environments the same value has to be a persistent environment
variable, which no command inside a session can set. Give them the lines to
paste, only the ones that differ from the defaults:

```
CLAUDE_PERSONAL_NOTES_REMOTE=<chosen-remote-or-url>
CLAUDE_PERSONAL_NOTES_BRANCH=<branch, only if not claude/personal-notes>
CLAUDE_PERSONAL_NOTES_PATH=<path, only if not .claude/personal/notes.md>
```

Point them at their environment's docs for where that list lives (for
Claude Code on the web:
<https://code.claude.com/docs/en/claude-code-on-the-web>), and at
[`personal-notes.env.example`](../../hooks/personal-notes.env.example) and
[`configure-personal-notes.sh`](../../hooks/configure-personal-notes.sh).
This part stays the user's to finish, so say so.

The branch and path have working defaults. Mention that both can be
overridden (`claude.personalNotesBranch` / `claude.personalNotesPath`), and
ask only if they want something else.

## 5. Run the setup

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" setup.personal_notes --remote <remote> \
  [--name "<name>" --email "<email>"] [--starter-notes]
```

`wait_for_basstler_install` returns at once unless a session start is still
installing the package this command runs, and waits for it otherwise; if it
fails, the install is still running after five minutes, so report that and
stop.

It refuses a remote GitHub says someone else owns (exit 3) before writing
anything. It records the remote in git config, creates the notes branch if
it's missing, seeds a notes file only if it didn't exist yet, records the
identity, and runs `session-start.sh`, which installs the package's
dependencies and writes `CLAUDE.local.md`. Then it reports which labels this
tooling uses are missing from the repository, and ends by printing
`check-setup.sh`'s report. It exits with that report's status: 0 when
nothing is left, 1 when something is or could not be verified.
Exit 4 means a hook script failed; its own output above says why.

The owner check and the label check need a GitHub token (`GH_TOKEN` or
`GITHUB_TOKEN`) and a notes remote on GitHub; without them the command says
it skipped both and carries on. A session usually has no token, so check the
labels with `mcp__github__get_label` instead, one call per label that
`"${BASSTLER_PYTHON}" -c 'from basstler.github_labels import GitHubLabel; print(*GitHubLabel)'`
lists. A `404` means missing.

**Labels are visible to everyone who sees the repository, so ask before
creating any.** If the user agrees, run the same command again with
`--create-labels`. Every other step is a no-op the second time. Where there
is no token, `"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" setup.steps` prints the
`gh label create` commands and the labels page for them. Missing labels don't
block anything else.

The notes it just wrote reach this conversation's context only at the next
session start; everything else is usable right away.

## 6. `stack_upstream` — the repository the project is reviewed on

Only when this row is `needs-setup`: an `info` row means nothing asked for an
upstream, and most projects have none.

The upstream is the repository the project's pull requests are reviewed on,
which is the user's to name. Ask for it as `<owner>/<name>`, offering as the
default the repository the clone's `upstream` remote points at, if it has
one. Then save it to their
personal `stack.toml`, which keeps it out of the project's tracked files:

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" setup.steps configure-upstream --repository <owner>/<name>
```

It keeps every other personal stack setting and replaces an upstream named
before. A project that wants every contributor to share the answer can commit
`upstream_repository` in `.claude/basstler/stack.toml` instead; the check
accepts either.

## 7. `upstream_reviews_action` — the fork's own upstream-reviews Action

Only once an upstream is named (the row says "not checked" otherwise). Unless
the row is `ok`, install it without asking - it is mechanical, and touches
nothing but a branch of its own on the user's fork:

```bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" setup.steps install-upstream-reviews-action --branch-or-tag "$(basstler_branch_or_tag)"
```

It creates a new branch named `basstler/upstream-reviews` on the user's fork,
with no history in common with the project's branches. The branch holds only a
README and a short workflow file that calls basstler's reusable workflow by
reference, so it works on a fork of any repository. Run again, it updates that
workflow to the basstler branch or tag this session's package was installed at,
which every session start also does once the branch exists.
Then tell
the user the one step left to them, which `"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" setup.steps` also
prints: a fork starts with Actions off, so they enable them once at
`https://github.com/<fork>/actions`. Until they do, `/upstream-reviews` reads
the upstream from the session instead.

## 8. `plan_site` — publish this repository's plans on the user's plan site

Unless the row is `ok`, which it is only once this clone's own repository stores
`PLAN_SITE_TOKEN` and its notes branch's latest dispatch run succeeded. Where the
credential may not read secrets, the row says so and judges by the runs alone.
Pass on what the row says: whether the repository stores the token, how many of its
dispatch runs failed, and the command it gives to store the token.

Every other repository on the site has a `plan_site_repository` row of its own,
always informational: mention one that stores no token, failed its latest run or
could not be read, but never judge the clone by it nor run step 8 for it.

The plan site builds in a repository the user owns, never in the project, and
which one is the user's to choose. When the notes branch already records one,
the row's command names it with `--site-repository`: ask the user only to
confirm it. Otherwise ask for it as `<owner>/<name>`, offering
`<their GitHub username>/plans` as the default. Then:

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" plan_site.publication --site-repository <owner>/<name>
```

The site builds with basstler's latest release, so it stays current with no re-run.

It reads the site repository's and this repository's workflow runs first and
writes nothing until it can. It authenticates with `GH_TOKEN` or
`GITHUB_TOKEN`, else with `gh`'s login. In a cloud session a read of the site
repository is refused (403) until it is attached: attach it with `add_repo`
(access `push`) and run the command again.

The build reads the registry, every repository it lists, and every repository
their plans' pull requests are on. If any of them is private, the build needs a
read-only token, stored on the site repository as `PLAN_SITE_READ_TOKEN`. Without
that secret, publication writes nothing and prints one step: store such a token,
or make those repositories public. The step warns that the site is public, so with
the token it shows what the build reads from them. Relay that warning and ask the
user which they want. When GitHub does
not say whether a repository is private or whether the secret is stored,
publication writes the files anyway and prints the same step, so the user can
check. A site published before basstler knew this secret passes no token: re-run
publication once the token is stored.

It then writes the site repository's workflow onto its default branch, lists
this repository in the hub file of the registry that workflow names (this
repository itself, the first time), and commits two workflows that start the
build: the notes branch's dispatch workflow, on every push to the notes branch,
and the default branch's merge workflow, on every pull request merged in this
repository. A fork gets no merge workflow, so its default branch stays as its
upstream's. The merge workflow never goes onto the default branch directly, so it
passes the repository's checks like any other change: it goes on
`basstler/plan-site-merge`, with a pull request opened for it and a step to
merge that pull request; when GitHub refuses to open it, the step says why and
gives the line that opens it.

It then prints the steps only the user can take, each with its copyable command
(where GitHub offers one) and the same steps numbered for github.com: creating
the site repository, turning on Pages, creating - or reusing - the fine-grained
token, storing it as the `PLAN_SITE_TOKEN` secret, and merging the merge
workflow. It exits 1 while any is left.

Actions secrets belong to one repository, and a user account has no shared
ones, so the token is stored in every repository the site publishes. The create
step's link opens GitHub's token form with the name, owner and Actions write
access filled in; only the site repository is picked by hand. The token reaches
the site repository alone, so it never changes when a repository joins. The store
step is one command the user runs in their own terminal, with their own `gh`
login: it asks for the token once at a hidden prompt, starts the site's build
with it - which proves the token and stores nothing when GitHub refuses it - then
stores it in every repository. In a cloud session the user has no terminal on the
session's machine, so the command printed there needs only `gh` and bash on the
user's own computer; the browser steps beside it need neither. Pass the command on
in its bash block, so it is copied whole. Never ask for the token in the chat, and
never run the command for the user: it reads the token only from a terminal. To add a repository later, the user clicks Regenerate token on the
existing token and runs the store command again; no new token is needed. A step
that follows a run shows that run's address, so the log says why it failed. Pass
the lines and the browser steps on exactly as printed, never shortened to one of
the two; once the user has done them, run the command again: it counts a step
done when a run that needs it succeeded.

## 9. Confirm, by re-running the check

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/check-setup.sh" $ARGUMENTS || true
```

Report what the second run says, not what you expect it to say. If a row is
still `needs-setup` or `unverified`, say which and why — a setup that
half-worked and was reported as finished is worse than one that reported the
truth. Call the clone set up only when the run exits 0 and `plan_site` is `ok`;
with `plan_site` `unverified`, say the plan site is *not verified*.

Then tell them what they can now do, briefly: ask for notes edits in any
session, track a PR's progress, and — if the dependencies installed —
`/plan-create`, pointing at
[`example-walkthrough.md`](../plan-create/example-walkthrough.md) for the
worked example.

## What this skill must never do

- **Never invent where someone's notes live.** A wrong remote pushes personal
  notes to a repository they didn't choose. Ask, always, unless the resolved
  remote is already provably their own.
- **Never claim the environment-variable half is done.** No command inside a
  session can persist an environment variable for the next fresh clone.
- **Never touch an existing personal-notes branch's contents.** Every write
  here is either creating a branch that provably doesn't exist yet, or a
  no-op-if-unchanged push of a file the user just asked for.
- **Never create labels in someone's repository unasked.** Labels are visible
  to everyone who sees the repository; report what's missing and offer.
- **Never read an `unverified` or `info` row as a pass.** Only `ok` is one.
