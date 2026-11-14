"""
Proposing one file for a repository's default branch.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from basstler.github.file_proposal import FileProposal
from basstler.repository import Repository

from ..constants.paths import DatasetLocation

# %% the page adding the file


def test_the_new_file_page_fills_in_the_file_s_path_and_content():
    text = DatasetLocation.REPOSITORY_TRUNK_DEFAULT_BRANCH.read_text()
    proposal = FileProposal(
        repository=Repository("an-owner", "a-project"),
        base="trunk",
        branch="a-proposal",
        file=".github/workflows/a-workflow.yml",
        text=text,
        title="Add a workflow",
        body="",
    )
    query = parse_qs(urlsplit(proposal.new_file_page).query)
    assert (query["filename"], query["value"]) == ([proposal.file], [text])
