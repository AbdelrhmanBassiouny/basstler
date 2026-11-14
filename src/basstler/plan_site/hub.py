#!/usr/bin/env python3
"""
The plan hub: every repository whose personal-notes branch holds plans, served as one site.

Each repository keeps its own plans. The hub file names the site they are published on,
the registry repository whose copy lists every repository, and that list. Every
registered repository's notes carry a copy, so a session anywhere knows the site and its
own place in it without reading another repository, under any account.

Usage:
    python3 -m basstler.plan_site.hub register --hub <hub.yaml> --repository <owner/repo> \\
        [--registry <owner/repo>] [--site-url <url>] --output <out>
    python3 -m basstler.plan_site.hub page-url --hub <hub.yaml> --repository <owner/repo> \\
        [--plan <plan-id> [--item <item-id>]]
    python3 -m basstler.plan_site.hub add-theme --hub <hub.yaml> --theme <theme.yaml> \\
        [--default] --output <out>

``register`` adds a repository to the hub file, creating the file (with this repository
as its own registry, unless one is named) when absent. It prints
``{"changed": true|false}``; push the output only when it changed.

``add-theme`` adds the theme a YAML file describes to the hub file's appearance
section, and with ``--default`` makes it the site's default. It fails, naming every
pairing, when the theme's text misses the WCAG AA contrast. It prints
``{"changed": true|false}``.

``page-url`` prints the address of a repository's page on the site, of one of its plans,
or of one item's card on that plan's page. It fails when the hub file names no site.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from basstler.class_property import classproperty
from basstler.git.commands import GitCommandRunner
from basstler.git.remote_branch import RemoteBranch
from basstler.github.repository import GitHubAddress, Repository
from basstler.locations import ProjectLocation
from basstler.plan_site.exceptions import RegistryUnreadableError
from basstler.plan_site.plan import Item
from basstler.plan_site.theme import (
    AppearanceSettings,
    SiteTheme,
)
from basstler.plan_site.workflows import PlanSiteSecret
from basstler.setup.steps import PersonalNotesSetting
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class HubCommand(StrEnum):
    """
    The subcommands the hub command runs.
    """

    REGISTER = "register"
    """
    List a repository in the hub file.
    """

    PAGE_URL = "page-url"
    """
    Print the address of a page on the site.
    """

    ADD_THEME = "add-theme"
    """
    Add a theme of the owner's to the hub file, or make it the default.
    """


class HubFileKey(StrEnum):
    """
    The keys a hub file is written with, each spelled once.
    """

    SITE_URL = "site_url"
    """
    The address the site is served from.
    """

    REGISTRY = "registry"
    """
    The repository whose copy of the file holds the complete list.
    """

    NOTES_BRANCH = "notes_branch"
    """
    The branch every listed repository keeps its notes on.
    """

    REPOSITORIES = "repositories"
    """
    Every repository the site publishes.
    """

    APPEARANCE = "appearance"
    """
    The site's default theme and colour scheme, and its owner's themes.
    """


@dataclass(frozen=True)
class SiteAddress:
    """
    The address a plan site is served from, and the address of every page on it.
    """

    site_url: str
    """
    The address the whole site is served from, with or without a trailing slash.
    """

    @property
    def hub_url(self) -> str:
        """
        The hub's address, which every page links back up to.
        """
        return f"{self.site_url.rstrip('/')}/"

    def repository_url(self, repository: Repository | str) -> str:
        """
        :param repository: The repository, as ``owner/repo``.
        :return: The address of that repository's index of plans.
        """
        return f"{self.hub_url}{repository}/"

    def plan_url(self, repository: Repository | str, plan_identifier: str) -> str:
        """
        :param repository: The repository whose notes hold the plan.
        :param plan_identifier: The plan's directory name.
        :return: The address the plan's page is served from.
        """
        return f"{self.repository_url(repository)}{plan_identifier}/"

    def item_url(
        self,
        repository: Repository | str,
        plan_identifier: str,
        item_identifier: str,
    ) -> str:
        """
        :param repository: The repository whose notes hold the plan.
        :param plan_identifier: The plan's directory name.
        :param item_identifier: The item's identifier.
        :return: The address of the item's card on its plan's page.
        """
        return (
            f"{self.plan_url(repository, plan_identifier)}"
            f"#{Item.anchor_of(item_identifier)}"
        )


@dataclass
class PlanHub:
    """
    The hub file's content.
    """

    registry: str
    """
    The ``owner/repo`` whose notes hold the complete list.
    """

    repositories: list[str] = field(default_factory=list)
    """
    Every ``owner/repo`` whose plans the site shows, in the order they are shown.
    """

    site_url: str | None = None
    """
    The address the site is served from, or ``None`` before one was chosen.
    """

    notes_branch: str = PersonalNotesSetting.BRANCH.default
    """
    The branch each listed repository keeps its notes on.
    """

    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    """
    The site's default theme and colour scheme, and the themes its owner adds.
    """

    @classproperty
    def file_header(cls) -> str:
        """
        The comment every written hub file opens with.
        """
        return (
            "# The plan hub. Generated by basstler.plan_site.hub: every listed repository's "
            "notes\n"
            "# carry a copy, and the registry's copy is the one whose list is complete. "
            "The\n"
            "# site is built from every listed repository's plans by basstler.plan_site.\n"
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> PlanHub:
        """
        :param data: The parsed hub file.
        :return: The hub it describes.
        """
        return cls(
            registry=data[HubFileKey.REGISTRY],
            repositories=list(data.get(HubFileKey.REPOSITORIES) or []),
            site_url=data.get(HubFileKey.SITE_URL),
            notes_branch=data.get(HubFileKey.NOTES_BRANCH)
            or PersonalNotesSetting.BRANCH.default,
            appearance=AppearanceSettings.from_json(
                data.get(HubFileKey.APPEARANCE) or {}
            ),
        )

    @classmethod
    def from_yaml(cls, text: str | None) -> PlanHub | None:
        """
        :param text: The hub file's content, which may be absent.
        :return: The hub, or ``None`` when there is no file or it is empty.
        """
        data = yaml.safe_load(text) if text else None
        return cls.from_mapping(data) if data else None

    @classmethod
    def load(cls, path: Path) -> PlanHub | None:
        """
        :param path: The hub file, which may not exist.
        :return: The hub, or ``None`` when the file is absent or empty.
        """
        return cls.from_yaml(path.read_text()) if path.is_file() else None

    @classmethod
    def from_registry(
        cls, registry: Repository, remote_root: str = GitHubAddress.WEB
    ) -> PlanHub | None:
        """
        Read the hub file off the registry's notes branch.

        :param registry: The repository whose notes hold the hub file.
        :param remote_root: Where repositories are fetched from, as
            :meth:`Repository.clone_url_under` takes it.
        :return: The hub file, or ``None`` when the registry has none.
        :raises RegistryUnreadableError: If the registry's notes branch cannot be
            fetched.
        """
        notes_branch = PersonalNotesSetting.BRANCH.default
        with tempfile.TemporaryDirectory() as scratch:
            notes = NotesBranch.fetch(
                registry, notes_branch, remote_root, Path(scratch)
            )
            if notes is None:
                raise RegistryUnreadableError(
                    registry,
                    notes_branch,
                    PlanSiteSecret.private_repository_correction,
                )
            text = notes.read(ProjectLocation.PLAN_HUB)
        return cls.from_yaml(text)

    def to_text(self) -> str:
        """
        :return: The hub file's content, header comment first.
        """
        data = {
            HubFileKey.SITE_URL.value: self.site_url,
            HubFileKey.REGISTRY.value: self.registry,
            HubFileKey.NOTES_BRANCH.value: self.notes_branch,
            HubFileKey.REPOSITORIES.value: self.repositories,
            HubFileKey.APPEARANCE.value: self.appearance.to_json(),
        }
        return self.file_header + yaml.safe_dump(data, sort_keys=False)

    @classmethod
    def published_repositories(
        cls,
        notes_branch: RemoteBranch,
        notes_repository: Repository,
        remote_root: str = GitHubAddress.WEB,
    ) -> list[Repository]:
        """
        :param notes_branch: The notes branch of *notes_repository*.
        :param notes_repository: The repository whose notes name the registry.
        :param remote_root: Where the registry is fetched from, as
            :meth:`Repository.clone_url_under` takes it.
        :return: *notes_repository*, then every other repository the registry's hub
            file lists.
        """
        # Only the registry's copy lists every repository; this one names the registry.
        own_copy = cls.from_yaml(notes_branch.read_latest(ProjectLocation.PLAN_HUB))
        if own_copy is None:
            return [notes_repository]
        hub = (
            cls.from_registry(Repository.parse(own_copy.registry), remote_root)
            or own_copy
        )
        listed = [Repository.parse(name) for name in hub.repositories]
        return list(dict.fromkeys([notes_repository, *listed]))

    def register(self, repository: str) -> bool:
        """
        :param repository: The ``owner/repo`` to list.
        :return: Whether it was not listed before.
        """
        if repository in self.repositories:
            return False
        self.repositories.append(repository)
        return True


@dataclass(frozen=True)
class PlanHistory:
    """
    When a plan was created and last changed on its notes branch.
    """

    created_at: datetime
    """
    The commit time of the first commit that wrote the plan.
    """

    modified_at: datetime
    """
    The commit time of the latest commit that changed it.
    """


@dataclass(frozen=True)
class NotesBranch:
    """
    One listed repository's notes branch, fetched into a scratch repository.
    """

    repository: Repository
    """
    The repository the branch belongs to.
    """

    git: GitCommandRunner
    """
    Runs git in the scratch repository the branch was fetched into.
    """

    @classmethod
    def fetch(
        cls,
        repository: Repository,
        branch: str,
        remote_root: str,
        scratch: Path,
        remote: str = "origin",
    ) -> NotesBranch | None:
        """
        :param repository: The repository to fetch from.
        :param branch: Its notes branch.
        :param remote_root: Where repositories are fetched from, as
            :meth:`Repository.clone_url_under` takes it.
        :param scratch: An empty directory of its own to fetch into.
        :param remote: The name the scratch repository gives the repository.
        :return: The fetched branch, or ``None`` when it cannot be fetched.
        """
        scratch.mkdir(parents=True, exist_ok=True)
        git = GitCommandRunner(scratch)
        git.run("init", "--quiet")
        git.run("remote", "add", remote, repository.clone_url_under(remote_root))
        # The whole history without old file contents dates each plan; checking a file
        # out downloads its content from the remote when it is needed.
        fetched = git.attempt("fetch", "--quiet", "--filter=blob:none", remote, branch)
        if not fetched.succeeded:
            logger.warning(
                f"{repository}: cannot fetch {branch}: {fetched.error_output}; "
                f"{PlanSiteSecret.private_repository_correction}"
            )
            return None
        return cls(repository, git)

    def read(self, path: Path) -> str | None:
        """
        :param path: A file's path relative to the branch's root.
        :return: The file's content, or ``None`` when the branch has no such file.
        """
        return self.git.file_at("FETCH_HEAD", path)

    def history_of(self, plan_directory_name: str) -> PlanHistory | None:
        """
        :param plan_directory_name: A plan's directory under the plans directory.
        :return: When the branch first and last changed it, ``None`` when it never did.
        """
        dates = self.git.run(
            "log",
            "--format=%cI",
            "FETCH_HEAD",
            "--",
            (ProjectLocation.PLANS / plan_directory_name).as_posix(),
        ).splitlines()
        if not dates:
            return None
        return PlanHistory(
            datetime.fromisoformat(dates[-1]), datetime.fromisoformat(dates[0])
        )

    def check_out_plans(self) -> Path:
        """
        Write the branch's plans directory out as plain files.

        :return: The plans directory, empty when the branch has none.
        """
        self.git.attempt(
            "checkout", "FETCH_HEAD", "--", ProjectLocation.PLANS.as_posix()
        )
        plans_directory = self.git.working_directory / ProjectLocation.PLANS
        plans_directory.mkdir(parents=True, exist_ok=True)
        return plans_directory


def main() -> int:
    """
    Parse arguments and run the subcommand. See the module docstring.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    register_parser = subcommands.add_parser(HubCommand.REGISTER)
    register_parser.add_argument("--hub", required=True, type=Path)
    register_parser.add_argument("--repository", required=True)
    register_parser.add_argument("--registry", default=None)
    register_parser.add_argument("--site-url", default=None)
    register_parser.add_argument("--output", required=True, type=Path)
    page_url_parser = subcommands.add_parser(HubCommand.PAGE_URL)
    page_url_parser.add_argument("--hub", required=True, type=Path)
    page_url_parser.add_argument("--repository", required=True)
    page_url_parser.add_argument("--plan", default=None)
    page_url_parser.add_argument("--item", default=None)
    add_theme_parser = subcommands.add_parser(HubCommand.ADD_THEME)
    add_theme_parser.add_argument("--hub", required=True, type=Path)
    add_theme_parser.add_argument("--theme", required=True, type=Path)
    add_theme_parser.add_argument("--default", action="store_true")
    add_theme_parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    if arguments.command == HubCommand.PAGE_URL:
        return print_page_url(arguments)
    if arguments.command == HubCommand.ADD_THEME:
        return add_theme(arguments)
    return register_repository(arguments)


def print_page_url(arguments: argparse.Namespace) -> int:
    """
    Print the address of the page ``page-url`` names.

    :param arguments: The parsed ``page-url`` arguments.
    :return: The exit status: 1 when the hub file names no site.
    """
    hub = PlanHub.load(arguments.hub)
    if hub is None or not hub.site_url:
        logger.error(f"{arguments.hub} names no plan site.")
        return 1
    site = SiteAddress(hub.site_url)
    if arguments.plan is None:
        logger.info(site.repository_url(arguments.repository))
    elif arguments.item is None:
        logger.info(site.plan_url(arguments.repository, arguments.plan))
    else:
        logger.info(site.item_url(arguments.repository, arguments.plan, arguments.item))
    return 0


def register_repository(arguments: argparse.Namespace) -> int:
    """
    List ``register``'s repository in the hub file and write the result.

    :param arguments: The parsed ``register`` arguments.
    :return: The exit status.
    """
    hub = PlanHub.load(arguments.hub)
    created = hub is None
    if created:
        hub = PlanHub(
            registry=arguments.registry or arguments.repository,
            site_url=arguments.site_url,
        )
    changed = hub.register(arguments.repository) or created
    if arguments.site_url and hub.site_url != arguments.site_url:
        hub.site_url = arguments.site_url
        changed = True
    arguments.output.write_text(hub.to_text())
    logger.info(json.dumps({"changed": changed}))
    return 0


def add_theme(arguments: argparse.Namespace) -> int:
    """
    Add ``add-theme``'s theme to the hub file and write the result.

    :param arguments: The parsed ``add-theme`` arguments.
    :return: The exit status: 1 when there is no hub file or the theme is hard to read.
    """
    hub = PlanHub.load(arguments.hub)
    if hub is None:
        logger.error(f"{arguments.hub} is not a hub file.")
        return 1
    theme = SiteTheme.from_json(yaml.safe_load(arguments.theme.read_text()))
    if theme.unreadable_pairings:
        logger.error(f"{theme.identifier}: {theme.contrast_report}")
        return 1
    appearance = hub.appearance.with_theme(theme)
    if arguments.default:
        appearance = replace(appearance, default_theme=theme.identifier)
    changed = appearance != hub.appearance
    hub.appearance = appearance
    arguments.output.write_text(hub.to_text())
    logger.info(json.dumps({"changed": changed}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
