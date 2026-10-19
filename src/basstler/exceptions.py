"""
krrood's ``DataclassException``, copied rather than imported, which is the boundary decision 12
records for this tooling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class DataclassException(Exception, ABC):
    """
    A base exception class for dataclass-based exceptions.
    Subclasses implement error_message() and suggest_correction(); both are evaluated at
    construction time and composed into the actual exception message (the args passed to
    Exception). A non-empty suggest_correction() is rendered as a trailing "Suggestion: ..." line.
    Subclasses that override __post_init__ must call super().__post_init__() at the end.
    """

    def __post_init__(self):
        # BaseException.__new__ bypasses the usual ABC instantiation check, so enforce it here.
        if getattr(type(self), "__abstractmethods__", None):
            raise TypeError(
                f"Can't instantiate abstract class {type(self).__name__} without an implementation of "
                f"{', '.join(sorted(type(self).__abstractmethods__))}."
            )
        message = self.error_message()
        correction = self.suggest_correction()
        if correction:
            message = f"{message}\nSuggestion: {correction}"
        super().__init__(message)

    def __str__(self) -> str:
        # Stdlib mixins like KeyError override __str__ to repr their args; always render the
        # plain message that __post_init__ baked into the args.
        return Exception.__str__(self)

    @abstractmethod
    def error_message(self) -> str:
        """
        :return: A human-readable description of what went wrong.
        """

    @abstractmethod
    def suggest_correction(self) -> str:
        """
        :return: Advice on how to fix the error, or an empty string if there is no specific advice.
        """
