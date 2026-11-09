#!/bin/bash
# A pre-commit hook standing in for a project's own checks: it rejects every commit, as
# pre-commit does in a checkout that has no .pre-commit-config.yaml.
echo "No .pre-commit-config.yaml file was found" >&2
exit 1
