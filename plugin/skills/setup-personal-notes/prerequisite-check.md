# Prerequisite check: running setup instead of failing

Every skill that reads or writes the personal-notes branch — `plan-create`,
`plan-item-kickoff`, `plan-item-resolve`, `add-plan-item`, `upstream-reviews` —
depends on a one-time setup the user may not have done yet, which otherwise fails
confusingly deep in the skill. Check first, and fix it.

## The procedure

Run the setup gate the skill's own document gives, **before** the skill's own first
step. It names the skill:

```bash
"${BASSTLER_PLUGIN_ROOT}/hooks/basstler.sh" setup.gate --skill <skill>; echo "setup gate exit status: $?"
```

`basstler.setup.gate` holds which checks each skill needs. The gate prints
`check-setup.sh`'s rows for those alone and exits for them alone, so a row the skill
does not use, such as `plan_site`, never stops it; the session start reports those.

**Exit code 0 — set up.** Say nothing about setup at all; carry straight on
with the skill. A user who is already set up must never hear about it.

**Exit code 1, and every row that is not `ok` or `info` is `in-progress`** — a
session start is installing it right now. Run
`source "${BASSTLER_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh" && wait_for_basstler_install`
in one call, then the gate again, and go on from what that second run says; never
install it yourself.

**A `*_access` row that is `needs-setup`** is not setup's: attach the repository it
names with `mcp__claude-code-remote__add_repo` (`access: "push"`), run its command, check
again. If the attach is refused, ask with `AskUserQuestion`, "Attach it (Recommended)"
first, saying why: saves then reach the site and the notes.

**Any other exit code 1 — something the skill needs is missing or not verified.** Do
not start the skill's real work, and do not attempt the individual fixes inline:
`/setup-personal-notes` exists to do exactly that, and duplicating a piece of it here
is how the two drift apart.

1. Tell the user, in one or two sentences, what is missing and that setup is
   running now — from the rows' own `<detail>` text, not a guess.
   This is a statement, not a question: never ask whether to run the setup.
2. Invoke `/setup-personal-notes` via the `Skill` tool and let it finish, passing it
   `--require-upstream` as its argument when the gate printed a `stack_upstream` row,
   so it checks the same things. It asks its own questions for the decisions that are
   genuinely the user's — which repository their notes live in, what goes in them,
   whether to create labels — and does the mechanical parts without asking.
3. Run the gate again. If it now exits 0, continue with the skill as though
   nothing had happened. If it still doesn't, report what remains unresolved and
   stop — do not push on into work that will fail later for the same reason.

**Any other exit status — the gate could not decide**, for one when run outside the
checkout. Report what it printed on standard error, fix that, and run it again; never
report setup as missing, or as done, because of it.
