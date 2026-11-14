"""
Reads and writes text as UTF-8, bytes without any encoding, and opens a request,
which is no file.
"""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

page = Path("page.html")
page.write_text("→", encoding="utf-8")
page.read_text(encoding="utf-8")
open(page, encoding="utf-8")
open(page, "rb")
page.open(mode="wb")
subprocess.run(["git", "log"], encoding="utf-8")
subprocess.run(["git", "log"], capture_output=True)
urllib.request.build_opener().open(urllib.request.Request("https://example.com"))
