"""
A Claude Code plugin's ``plugin.json``, read by a test.

Several suites read the plugin's name back, so the manifest's keys live here once rather
than at every use site. It names no version: a release is only a tag on its merge commit.
The marketplace's own ``marketplace.json`` is read here too.
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
    The release a manifest names: only the released plugin's names one.
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
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            name=manifest[PluginManifestKey.NAME],
        )

    @classmethod
    def of_this_plugin(cls) -> PluginManifest:
        """
        :return: This repository's own plugin manifest.
        """
        return cls.read(RepositoryLocation.PLUGIN_MANIFEST)


class MarketplaceKey(StrEnum):
    """
    The keys of a Claude Code ``marketplace.json`` the suites read.
    """

    PLUGINS = "plugins"
    """
    The plugins the marketplace lists.
    """

    SOURCE = "source"
    """
    Where a listed plugin is served from.
    """

    REPOSITORY = "repo"
    """
    The GitHub repository, as ``owner/name``, the plugin is served from.
    """

    REF = "ref"
    """
    The branch or tag of that repository the plugin is served at.
    """


@dataclass(frozen=True)
class PluginSource:
    """
    Where a marketplace serves its one plugin from: a GitHub repository at a ref.
    """

    repository: str
    """
    The repository, as ``owner/name``.
    """

    ref: str
    """
    The branch or tag the plugin is served at.
    """

    @classmethod
    def of_this_marketplace(cls) -> PluginSource:
        """
        :return: Where this repository's marketplace serves the plugin from.
        """
        marketplace = json.loads(
            RepositoryLocation.MARKETPLACE.read_text(encoding="utf-8")
        )
        (plugin,) = marketplace[MarketplaceKey.PLUGINS]
        source = plugin[MarketplaceKey.SOURCE]
        return cls(
            repository=source[MarketplaceKey.REPOSITORY], ref=source[MarketplaceKey.REF]
        )
