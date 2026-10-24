"""
The GitHub labels this tooling reads or applies, in one table.

The dashboard reads some of them, a maintenance pass writes one, and setup creates
all of them on a fork. One enum names them all, so a label one part recognizes cannot be
missing from the set setup creates.

Kept free of third-party imports, so the setup script can read it before the dashboard's
dependencies are installed.
"""

from __future__ import annotations

from enum import StrEnum

from basstler.repository import Repository


class GitHubLabel(StrEnum):
    """
    Every label this tooling reads or applies, and therefore every one a fork must
    carry, each with the description it is created with.

    A member is its own label name, so it compares equal to the label as GitHub returns
    it.
    """

    purpose: str
    """
    What the label means, used as its description when it is created.
    """

    def __new__(cls, label: str, purpose: str) -> GitHubLabel:
        """
        Make a member that is its own label name and carries what the label means.

        :param label: The label's name, as GitHub stores it.
        :param purpose: What it means, used as the description when it is created.
        :return: The member.
        """
        member = str.__new__(cls, label)
        member._value_ = label
        member.purpose = purpose
        return member

    MERGED = ("merged", "The changes landed even though GitHub never recorded a merge")
    """
    Read by the dashboard, which treats the label exactly like a real merge.
    """

    IN_REVIEW = ("in-review", "Under review")
    """
    Recognized so it does not read as an unknown label; no script acts on it yet.
    """

    BUG = ("bug", "A bug fix")
    """
    Applied by a session opening a bug-fix pull request, and shown as a dashboard chip.
    """

    PROMOTION_LINK_SENT = (
        "promotion-link-sent",
        "A maintenance pass has written this branch's upstream create-link",
    )
    """
    Applied by a maintenance pass to a fork pull request whose link it has built,
    so a later pass does not rebuild it.
    """

    def creation_command(self, repository: Repository) -> str:
        """
        The ``gh`` command that creates this label.

        :param repository: The repository to create it in.
        :return: The command, ready to paste.
        """
        return (
            f"gh label create {self.value} --repo {repository.full_name} "
            f'--description "{self.purpose}"'
        )
