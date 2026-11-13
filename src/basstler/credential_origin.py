"""
Naming where a GitHub token came from, so a refusal can say which token to renew.
"""

from __future__ import annotations


class CredentialOrigin:
    """
    Where the token a GitHub request authenticates with comes from.
    """

    def describe_credential(self) -> str:
        """
        :return: The token, named by where it came from.
        """
        raise NotImplementedError

    def suggest_renewal(self) -> str:
        """
        :return: How to replace the token with a valid one.
        """
        raise NotImplementedError
