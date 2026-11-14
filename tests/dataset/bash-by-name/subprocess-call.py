"""
Runs bash by its name, which Windows resolves to WSL's launcher.
"""

from __future__ import annotations

import subprocess

subprocess.run(["bash", "-c", "true"], check=True)
