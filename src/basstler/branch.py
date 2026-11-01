"""
A git branch, the base of every branch the package handles.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.class_property import classproperty

# %% the branch


@dataclass(frozen=True)
class Branch:
    """
    A named branch of a git repository.
    """

    name: str
    """
    The branch's name, without the namespace it is kept under.
    """

    @classproperty
    def namespace(cls) -> str:
        """
        The namespace every branch is kept under in a repository.
        """
        return "refs/heads"

    @property
    def reference(self) -> str:
        """
        :return: The full reference the branch is kept under.
        """
        return f"{self.namespace}/{self.name}"
