# basstler-package — standing rules

- After basstler-v3 (#99) lands, build every item here on v3, not v2: plans are tracking issues (not plan.yaml), pages render on the Pages plan site (not the Artifact dashboard), code runs through the basstler CLI (not bash hooks or python -m modules), and v3's roadmap rules apply. Read any v2 piece a rule names as its v3 replacement; rewrite an item's notes before starting it.
- New tooling work starts here, on `main`, as a draft pull request. Carried branches get main merged in (never rebased) before their pull request opens.
- Setup is scripted: a skill only asks the questions, and every mechanical step is a `basstler.setup_steps` subcommand with a `check-setup.sh` row. No user copies files by hand.
- Development tooling shared with other repositories comes from a pinned, published package, never a copied script.
- External data (API responses, JSON, files) is parsed into dataclass models at the boundary, and every decision afterwards is made on the models, never on raw dicts. Each model reads only its own object's fields and delegates nested objects to their own models (agreed at https://github.com/AbdelrhmanBassiouny/basstler/pull/13#discussion_r4316972597).
