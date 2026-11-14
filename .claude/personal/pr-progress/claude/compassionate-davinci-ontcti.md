**Plan**
- Move the plan validation problems into plan.exceptions
- git: CommitTrailer and IntegrationStrategy into git; GitHubLoginLendingRunner into github; BranchAncestry and commit_move into stack; publishing takes the remote
- RemoteBranch.repository/description into a github subclass
- UpstreamReadError and GraphQLErrorsReturned into github.exceptions; the open-pull-requests request into upstream_reviews; the upstream setting into github
- live_pull_requests_of takes references
- Plan model into basstler.plan, with a hub-side card for the render fields
- Reorder the layers so notes sits below plan; update the standing rule; post the follow-up split item on #151

**Done**
- Draft PR #217 opened; item recorded as in progress

**Next**
- First move: the plan validation problems
