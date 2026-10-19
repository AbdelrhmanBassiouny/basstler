"""
A Claude Code plugin's ``plugin.json``, read by a test.

Several suites read the plugin's name and version back, so the manifest's keys and the
form its release tag takes live here once rather than at every use site.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .constants.paths import RepositoryLocation


class PluginManifestKey(StrEnum):
    """
    The keys of a Claude Code plugin's ``plugin.json`` the suites read.
    """

    NAME = "name"
    """
    The plugin's name, which is also its package's distribution name.
    """

    VERSION = "version"
    """
    The plugin's release, which its package is installed at.
    """


@dataclass(frozen=True)
class PluginManifest:
    """
    The parts of a ``plugin.json`` the suites read.
    """

    name: str
    """
    The plugin's name, which is also its package's distribution name.
    """

    version: str
    """
    The plugin's release, which its package is installed at.
    """

    @classmethod
    def read(cls, path: Path) -> PluginManifest:
        """
        :param path: A ``plugin.json``.
        :return: Its name and version.
        """
        manifest = json.loads(path.read_text())
        return cls(
            name=manifest[PluginManifestKey.NAME],
            version=manifest[PluginManifestKey.VERSION],
        )

    @classmethod
    def of_this_plugin(cls) -> PluginManifest:
        """
        :return: This repository's own plugin manifest.
        """
        return cls.read(RepositoryLocation.PLUGIN_MANIFEST)

    @property
    def release_tag(self) -> str:
        """
        :return: The tag the release workflow puts on this version.
        """
        return f"v{self.version}"
