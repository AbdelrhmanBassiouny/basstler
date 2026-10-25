Draft #60 (bug), off main.

## Plan
- `plan_item_bootstrap record` indents a new item like the manifest's existing items.

## Done
- Root cause: `render_new_item` used the fixed `ItemLayout` indent; flush-indented
  manifests (save-plan.sh's own dump) stopped parsing. Fixed via `ItemIndentation` read
  off the manifest; test on `narrowly-indented-plan.yaml`. 1136 pass.

## Next
- Waiting on review and CI. #48 carries an older rewrite of the same writer; keep this
  behaviour when it merges main.
