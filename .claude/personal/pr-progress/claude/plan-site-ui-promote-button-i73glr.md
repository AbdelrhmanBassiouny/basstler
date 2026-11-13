## Plan
- Extract one promotability rule (reasons a branch is not promotable) shared by `Stack.promotion_order` and the site
- Narrow `PromotionLink.build` to a target dataclass (upstream repository, base, fork owner)
- Read fork parent + default branch, and PR base/title, into the site build
- Render a new-tab link, or a disabled control with the reason as hover text

## Done
- Bootstrapped branch, draft PR #211, item recorded in progress

## Next
- Tests first for the shared rule, then the code
