"""
Reads and writes text in the locale encoding, which on Windows cannot encode most of
Unicode.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

page = Path("page.html")
page.write_text("→")
page.read_text()
open(page)
page.open("w")
subprocess.run(["git", "log"], text=True)
