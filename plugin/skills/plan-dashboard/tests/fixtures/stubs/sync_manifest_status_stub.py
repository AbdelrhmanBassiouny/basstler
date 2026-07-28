#!/usr/bin/env python3
"""
Stand-in for sync_manifest_status.py used by test_refresh_dashboard_sh.py: reports
whichever "corrected" list the test asked for, via an environment variable, instead of
reading a real plan.yaml.
"""

import json
import os

print(json.dumps({"corrected": json.loads(os.environ["SYNC_STUB_CORRECTED_JSON"])}))
