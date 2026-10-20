# basstler-package — standing rules

- New tooling work starts here, on `main`, as a draft pull request. Carried branches get main merged in (never rebased) before their pull request opens.
- Setup is scripted: a skill only asks the questions, and every mechanical step is a `basstler.setup_steps` subcommand with a `check-setup.sh` row. No user copies files by hand.
- Development tooling shared with other repositories comes from a pinned, published package, never a copied script.
- External data (API responses, JSON, files) is parsed into dataclass models at the boundary, and every decision afterwards is made on the models, never on raw dicts. Each model reads only its own object's fields and delegates nested objects to their own models (agreed at https://github.com/AbdelrhmanBassiouny/basstler/pull/13#discussion_r4316972597).
