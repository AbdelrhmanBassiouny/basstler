"""
An email address, read out of the text a user types.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.exceptions import MalformedEmailAddressError

# %% the address


@dataclass(frozen=True)
class EmailAddress:
    """
    An email address, written as its text wherever a string is expected.
    """

    local_part: str
    """
    The part before the last ``@``: the mailbox.
    """

    domain: str
    """
    The part after the last ``@``: the host that receives the mail.
    """

    @classproperty
    def separator(cls) -> str:
        """
        What separates the local part from the domain.
        """
        return "@"

    @classmethod
    def parse(cls, text: str) -> EmailAddress:
        """
        Parse a ``local-part@domain`` address.

        :param text: The address to parse.
        :return: The parsed address.
        :raises MalformedEmailAddressError: If *text* lacks a local part or a domain.
        """
        local_part, separator, domain = text.rpartition(cls.separator)
        if not (local_part and separator and domain):
            raise MalformedEmailAddressError(text)
        return cls(local_part, domain)

    def __str__(self) -> str:
        """:return: The address as it is written."""
        return f"{self.local_part}{self.separator}{self.domain}"
