"""
Runs the bash :class:`basstler.bash.Bash` locates, and lists names that are no command.
"""

from __future__ import annotations

import os
import subprocess

from basstler.bash import Bash

subprocess.run(Bash.locate(os.environ).command("-c", "true"), check=True)

MODULE_NAMES = ("bash", "git")
