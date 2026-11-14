Plan (review-triage/mechanical-file-triage, draft #213; follow-ups draft #214, #215):
- #213: extensible basstler-review-triage distribution, CI summary, mark-viewed
- #214: keyword arguments; module, definition and file-path moves; relative imports
- #215: mark viewed on every PR or on demand; set-up-mark-viewed; README; skill

Done:
- #214: #210 now 233/246 mechanical (13 left are real changes); 2353 tests green
- #215: set-up-mark-viewed (forks written; others get a PR from basstler/mark-viewed or
  a pre-filled new-file link), runs skip without a token, unreadable steps reported as
  such; basstler's own every-PR caller; 2348 tests green at 63c7022f

Next:
- User: store REVIEW_TRIAGE_VIEWER_TOKEN on basstler, merge #215, re-run set-up-mark-viewed
- Follow-up suggested: plan site onto github.token_form (needs a test change)
- Possible: path literals following a moved directory (#210 locations.py)
