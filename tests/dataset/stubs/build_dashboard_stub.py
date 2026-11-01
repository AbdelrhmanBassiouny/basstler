#!/usr/bin/env python3
"""
Stand-in for dashboard/plan_page.py used by hooks/test_refresh_dashboard.py: records its
own invocation arguments to a file (so the test can inspect what refresh_dashboard.sh
passed it, e.g. whether --tracking-url was forwarded) and prints a minimal summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

Path(f"{Path(__file__).stem}_invocation.json").write_text(json.dumps(sys.argv[1:]))
print(json.dumps({"drift_count": 0}))
