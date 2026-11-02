#!/bin/bash
# A pre-receive hook standing in for a protected default branch: it refuses every push
# that updates main and accepts the rest.
set -euo pipefail

while read -r _old _new reference; do
    if [ "${reference}" = "refs/heads/main" ]; then
        echo "main is protected" >&2
        exit 1
    fi
done
