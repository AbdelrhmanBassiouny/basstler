Plan (review-triage/mechanical-file-triage, draft #213; follow-ups draft #214, #215):
- #213: extensible basstler-review-triage distribution, CI summary, mark-viewed
- #214: keyword arguments; module, definition and file-path moves; relative imports
- #215: mark viewed on every PR or on demand; set-up-mark-viewed; README; skill

Done:
- #214: #210 now 233/246 mechanical (13 left are real changes); 2353 tests green
- #215: set-up-mark-viewed (forks only written), mark-viewed falls back to Actions,
  FilesNotMarkedViewed names both routes + README; 2340 tests green at c6f8ca4e

Next:
- User: run set-up-mark-viewed --on-every-pull-request, store the token
- Follow-up suggested: plan site onto github.token_form (needs a test change)
- Possible: path literals following a moved directory (#210 locations.py)
