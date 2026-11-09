#!/bin/bash
# A pre-receive hook standing in for GitHub refusing a token without the workflow scope:
# it refuses every push with the message GitHub gives.
set -euo pipefail

echo 'refusing to allow an OAuth App to create or update workflow `.github/workflows/plan-site.yml` without `workflow` scope' >&2
exit 1
