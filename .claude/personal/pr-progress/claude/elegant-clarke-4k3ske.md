## PR progress: skill-document-links (#74)

Plan
- Replace `${*_DOCUMENT}` skill references with relative links; drop unused variables; guard with tests

Done
- 21 references replaced, 5 variables (+ADD_PLAN_ITEM_DIRECTORY) dropped, tests added (233eae2)
- PR description and manifest notes current

Next
- Await review/CI; 14 full-suite failures pre-exist on main in-session - check CI shows the same
- Possible follow-up: unused SETUP_PREREQUISITE_DOCUMENT, STARTER_NOTES_FILE
