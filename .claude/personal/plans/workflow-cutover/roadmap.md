# workflow-cutover — standing rules

Moved from the CRAM fork's notes on 2026-10-18. An item carrying `repository: AbdelrhmanBassiouny/cognitive_robot_abstract_machine` still points at its CRAM-fork pull request; basstler-package's basstler-open-pull-request-carryover reopens it here and clears that line.

- The site lives on a regenerated branch. The workflow runs from the fork's default branch, which is the integration branch, and that branch is rebuilt from scratch - a rebuild that drops the tip carrying the workflow takes it off the default branch and manual dispatch stops being offered until a later build carries it again.
- The base-change credential is unverified in the Action. A session's own git-proxy credential refuses a base change while its MCP client performs one; the Action's credential is a third identity again. Verify it with a real base change before relying on it.
- Two operations stay outside the harness. Tag pushes and branch deletes get a 403 through a session's git proxy and no tool substitutes, so `tooling-branch-retirement`'s last two steps are the user's to run. A session can do every verification and prepare the exact commands.
- Site code names nothing twice. Locations, branch names, repository URLs, REST fields and pull request states come from what the package already defines (`ProjectLocation`, `PersonalNotesSetting`, `Repository`, `PullRequestField`, `PullRequestState`), git runs through `GitCommandRunner`, every page renders through `TemplatePage`, and tests read their values from the dataset or those enums (owner review of #6, 2026-10-18).
