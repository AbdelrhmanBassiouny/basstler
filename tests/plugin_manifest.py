"""
A Claude Code plugin's ``plugin.json``, read by a test.

Several suites read the plugin's name back, so the manifest's keys live here once rather
than at every use site. It names no version: a release is only a tag on its merge commit.
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
    The key a manifest would pin a release with, which this plugin's leaves out.
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

    @classmethod
    def read(cls, path: Path) -> PluginManifest:
        """
        :param path: A ``plugin.json``.
        :return: Its name.
        """
        manifest = json.loads(path.read_text())
        return cls(
            name=manifest[PluginManifestKey.NAME],
        )

    @classmethod
    def of_this_plugin(cls) -> PluginManifest:
        """
        :return: This repository's own plugin manifest.
        """
        return cls.read(RepositoryLocation.PLUGIN_MANIFEST)
