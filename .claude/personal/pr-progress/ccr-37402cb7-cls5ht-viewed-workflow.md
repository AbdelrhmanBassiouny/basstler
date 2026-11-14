Plan (review-triage/mechanical-file-triage, draft #213; follow-ups draft #214, #215):
- #213: extensible basstler-review-triage distribution, CI summary, mark-viewed
- #214: keyword arguments; module, definition and file-path moves; relative imports
- #215: mark viewed on every PR or on demand; set-up-mark-viewed; README; skill

Done:
- #214: #210 now 233/246 mechanical (13 left are real changes); 2353 tests green
- #215: set-up-mark-viewed (forks written; others get a PR or a pre-filled new-file
  link), runs skip without a token; one token for the plan site and mark-viewed where
  the owners match (plan_site.publication --mark-viewed-on); token steps say "unless
  stored already" when the secret cannot be read

Next:
- User: review and merge #213 then #215 (merging left to the user); re-run
  set-up-mark-viewed afterwards
- Follow-up suggested: plan site onto github.token_form (needs a test change)
- Possible: path literals following a moved directory (#210 locations.py)
