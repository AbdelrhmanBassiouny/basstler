"""
A plan's two documents on the personal-notes branch, and the checkout they are read
through.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from basstler.bash import Bash
from basstler.locations import PluginLocation, ProjectLocation
from basstler.plan.item_bootstrap.exceptions import (
    NotesBranchUnavailableError,
    PlanNotWrittenError,
    PlanSaveRefusedError,
    UnknownItemError,
    UnknownPlanError,
)
from basstler.plan.dependencies import PlanDirectory
from basstler.plan.model import (
    ManifestKey,
    PlanDocument,
    PlanManifest,
)
from basstler.plugin_root import PluginRoot
from basstler.shell_configuration import (
    FetchedBranchReference,
    ShellConfigurationFunction,
)

# %% the plan on the personal-notes branch


@dataclass(frozen=True)
class ProjectCheckout:
    """
    The repository a plan item is bootstrapped in, and the git commands run within it.
    """

    project_root: Path
    """
    The repository to run within.
    """

    def run_git(self, *arguments: str) -> str:
        """
        Run git in the checkout and return its standard output.

        :param arguments: The arguments to pass to git.
        :raises subprocess.CalledProcessError: If git reports an error.
        :return: Standard output, stripped of its trailing newline.
        """
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.rstrip("\n")

    def fetch_notes_branch(self) -> None:
        """
        Fetch the personal-notes branch into
        :attr:`FetchedBranchReference.PERSONAL_NOTES`.

        Calls the shell configuration's own fetch function, so this and the hook scripts
        never disagree about which branch a plan is on.

        :raises NotesBranchUnavailableError: If the notes branch cannot be fetched.
        """
        probe = ShellConfigurationFunction.FETCH_PERSONAL_NOTES_BRANCH.run(
            self.project_root
        )
        if probe.returncode != 0:
            raise NotesBranchUnavailableError(
                detail=probe.stderr.strip() or "no personal-notes branch found"
            )

    def branch_is_published(self, branch: str, remote: str) -> bool:
        """
        :param branch: The branch to look for.
        :param remote: The remote to ask.
        :return: Whether *remote* already carries *branch*.
        """
        return bool(self.run_git("ls-remote", "--heads", remote, branch).strip())

    def check_out_manifests(self, destination: Path) -> PlanDirectory:
        """
        Write every plan's manifest on the fetched notes branch out as plain files.

        :param destination: An empty directory to write into, one subdirectory per plan.
        :return: The plans the manifests were written to.
        """
        listing = self.run_git(
            "ls-tree",
            "-r",
            "--name-only",
            FetchedBranchReference.PERSONAL_NOTES,
            str(ProjectLocation.PLANS),
        )
        for path in map(PurePosixPath, listing.splitlines()):
            if (
                path.name != PlanDocument.MANIFEST
                or path.parent.parent != PurePosixPath(ProjectLocation.PLANS)
            ):
                continue
            manifest = destination / path.parent.name / PlanDocument.MANIFEST
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                self.run_git(
                    "show", FetchedBranchReference.PERSONAL_NOTES.file_at(path)
                )
                + "\n"
            )
        return PlanDirectory(destination)

    def plan_tracking(self, branch: str) -> str | None:
        """
        The plan that tracks *branch*, per the branch index on the freshly fetched notes
        branch.

        :param branch: The branch to look up.
        :raises NotesBranchUnavailableError: If the notes branch cannot be fetched.
        :return: The plan's id, or ``None`` when no plan claims the branch.
        """
        self.fetch_notes_branch()
        lookup = ShellConfigurationFunction.PLAN_ID_FOR_BRANCH.run(
            self.project_root, branch
        )
        return lookup.stdout.strip() or None


@dataclass(frozen=True)
class PlanDocuments:
    """
    One plan's manifest and roadmap as they stand on the personal-notes branch.
    """

    plan_identifier: str
    """
    The plan's id.
    """

    manifest_text: str
    """
    The manifest's raw text, patched by line rather than re-serialized.
    """

    roadmap_text: str
    """
    The roadmap's raw markdown.
    """

    @classmethod
    def load(cls, plan_identifier: str, project_root: Path) -> PlanDocuments:
        """
        Read a plan's manifest and roadmap off the freshly fetched notes branch.

        The fetch happens here, immediately before the caller's edit, so an edit is
        never applied to a copy loaded earlier in the session.

        :param plan_identifier: The plan's id.
        :param project_root: The repository to read within.
        :raises UnknownPlanError: If the plan has no manifest on the branch.
        :return: The loaded documents.
        """
        checkout = ProjectCheckout(project_root)
        checkout.fetch_notes_branch()
        contents = {}
        for document in PlanDocument:
            path = document.path_within_notes_branch(plan_identifier)
            try:
                contents[document] = (
                    checkout.run_git(
                        "show", FetchedBranchReference.PERSONAL_NOTES.file_at(path)
                    )
                    + "\n"
                )
            except subprocess.CalledProcessError as error:
                raise UnknownPlanError(
                    plan_identifier=plan_identifier, manifest_path=path
                ) from error
        return cls(
            plan_identifier=plan_identifier,
            manifest_text=contents[PlanDocument.MANIFEST],
            roadmap_text=contents[PlanDocument.ROADMAP],
        )

    @property
    def manifest(self) -> dict[str, Any]:
        """
        The parsed manifest, for reading fields rather than editing them.
        """
        return yaml.safe_load(self.manifest_text)

    def repository_for(self, item_identifier: str) -> str:
        """
        The ``owner/repo`` an item's pull request belongs to.

        :param item_identifier: The item's id.
        :raises UnknownItemError: If no item carries that id.
        :return: The item's own repository, or the plan's default one.
        """
        item = self.item(item_identifier)
        return (
            item.get(ManifestKey.REPOSITORY.key)
            or self.manifest[ManifestKey.DEFAULT_REPOSITORY.key]
        )

    def item(self, item_identifier: str) -> dict[str, Any]:
        """
        One item's parsed mapping.

        :param item_identifier: The item's id, or its branch when it has no id.
        :raises UnknownItemError: If no item matches.
        :return: The item's mapping.
        """
        for candidate in self.manifest.get(ManifestKey.ITEMS.key, []):
            identifier = candidate.get(ManifestKey.IDENTIFIER.key) or candidate.get(
                ManifestKey.BRANCH.key
            )
            if identifier == item_identifier:
                return candidate
        raise UnknownItemError(
            plan_identifier=self.plan_identifier, item_identifier=item_identifier
        )

    def has_item(self, item_identifier: str) -> bool:
        """
        Whether the plan already tracks an item under *item_identifier*.

        :param item_identifier: The item's id.
        :return: True when an entry exists.
        """
        try:
            self.item(item_identifier)
        except UnknownItemError:
            return False
        return True

    def save(self, manifest_text: str, roadmap_text: str, project_root: Path) -> None:
        """
        Push an edited manifest and roadmap through ``save-plan.sh``, then read the
        notes branch back to confirm they landed.

        :param manifest_text: The full manifest to write.
        :param roadmap_text: The full roadmap to write.
        :param project_root: The repository to run the script from.
        :raises PlanSaveRefusedError: If the script refuses the documents.
        :raises PlanNotWrittenError: If the branch does not carry the edit afterwards.
        """
        with tempfile.TemporaryDirectory() as scratch_directory:
            scratch = Path(scratch_directory)
            written = {
                PlanDocument.MANIFEST: manifest_text,
                PlanDocument.ROADMAP: roadmap_text,
            }
            for document, content in written.items():
                (scratch / document.value).write_text(content)
            saved = subprocess.run(
                Bash.locate(os.environ).command(
                    PluginRoot.locate(os.environ).path_of(
                        PluginLocation.PLAN_SAVING_SCRIPT
                    ),
                    self.plan_identifier,
                    "--manifest",
                    str(scratch / PlanDocument.MANIFEST.value),
                    "--roadmap",
                    str(scratch / PlanDocument.ROADMAP.value),
                ),
                cwd=project_root,
                capture_output=True,
                text=True,
            )
        if saved.returncode != 0:
            raise PlanSaveRefusedError(detail=saved.stderr.strip())
        self.confirm_written(written, project_root)

    def confirm_written(
        self, written: dict[PlanDocument, str], project_root: Path
    ) -> None:
        """
        Check that the notes branch carries what was just saved, as the save stores it:
        the manifest without its landed items.

        :param written: The content each document was saved with.
        :param project_root: The repository to read within.
        :raises PlanNotWrittenError: If a document on the branch differs from what was
            saved.
        """
        landed = PlanDocuments.load(self.plan_identifier, project_root)
        expected = {
            PlanDocument.MANIFEST: PlanManifest(
                yaml.safe_load(written[PlanDocument.MANIFEST])
            )
            .without_landed_items()
            .content,
            PlanDocument.ROADMAP: written[PlanDocument.ROADMAP].strip(),
        }
        on_the_branch = {
            PlanDocument.MANIFEST: landed.manifest,
            PlanDocument.ROADMAP: landed.roadmap_text.strip(),
        }
        unwritten = tuple(
            document
            for document in written
            if on_the_branch[document] != expected[document]
        )
        if unwritten:
            raise PlanNotWrittenError(
                plan_identifier=self.plan_identifier, documents=unwritten
            )
