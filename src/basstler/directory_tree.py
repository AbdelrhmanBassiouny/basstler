"""
Removing a directory and everything in it, read-only entries included.
"""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# %% the tree


@dataclass(frozen=True)
class DirectoryTree:
    """
    A directory and everything in it, such as a clone whose object files git left
    read-only, which Windows refuses to delete.
    """

    root: Path
    """
    The directory at the top of the tree.
    """

    def remove(self) -> None:
        """
        Delete the tree, making each entry that refuses deletion writable first; a tree
        that is not there is left as it is.
        """
        if not self.root.exists():
            return
        shutil.rmtree(self.root, onexc=self.remove_writable)

    @staticmethod
    def remove_writable(
        removal: Callable[[str], object], path: str, refusal: BaseException
    ) -> None:
        """
        Make *path* and the directory holding it writable, then remove it again.

        :param removal: The function that refused to remove *path*.
        :param path: The entry it refused.
        :param refusal: Why it refused, raised again when it is not a permission error.
        """
        if not isinstance(refusal, PermissionError):
            raise refusal
        writable = stat.S_IRWXU
        os.chmod(os.path.dirname(path), writable)
        os.chmod(path, writable)
        removal(path)
