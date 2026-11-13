## Plan
- Shared promotability rule (done); PromotionLink built for a target (done)
- Site reads the PR base/title and the fork's upstream (done)
- Card button: new-tab link or disabled with reason (done, under full-suite check)

## Done
- `PromotionReadiness` / `PromotionBlocker` used by `Stack.promotion_order` and the site
- `PromotionTarget` + `PromotionLink.for_target`; `build` keeps its signature
- `ForkLineage` read from repository details; `PromotionButton` on `Item.promotion`

## Next
- Confirm the full suite, push, then document the button in the plan-site docs
