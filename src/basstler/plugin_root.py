"""
The root of the plugin whose scripts and skill files this package runs and reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from basstler.exceptions import PluginRootNotADirectoryError, PluginRootUnsetError
from basstler.locations import BasstlerVariable, PluginLocation, PluginSkillLocation

# %% the plugin root


@dataclass(frozen=True)
class PluginRoot:
    """
    The directory holding the plugin's manifest, hooks and skills.
    """

    directory: Path
    """
    The plugin's root directory.
    """

    @classmethod
    def locate(cls, environment: Mapping[str, str]) -> PluginRoot:
        """
        Find the plugin the environment exports, which sourcing its shell configuration
        does.

        :param environment: The environment the plugin's scripts will run in.
        :return: The plugin root exported.
        :raises PluginRootUnsetError: If no plugin root is exported.
        :raises PluginRootNotADirectoryError: If the exported root is not a directory.
        """
        exported = environment.get(BasstlerVariable.PLUGIN_ROOT)
        if not exported:
            raise PluginRootUnsetError()
        directory = Path(exported)
        if not directory.is_dir():
            raise PluginRootNotADirectoryError(directory)
        return cls(directory)

    def path_of(self, location: PluginLocation | PluginSkillLocation) -> Path:
        """
        :param location: A file of the plugin.
        :return: That file in this plugin.
        """
        return self.directory / location
