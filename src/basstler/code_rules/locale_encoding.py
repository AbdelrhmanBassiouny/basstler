"""
Finds text read or written in the locale encoding, which on Windows is a code page that
cannot encode most of Unicode.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import override

from basstler.code_rules.checker import CodeRuleChecker, CodeRuleViolation

# %% what reads and writes text


class TextFunction(StrEnum):
    """
    The functions and methods that read or write text in the locale encoding unless
    given one.
    """

    READ_TEXT = "read_text"
    """
    :meth:`pathlib.Path.read_text`.
    """

    WRITE_TEXT = "write_text"
    """
    :meth:`pathlib.Path.write_text`.
    """

    OPEN = "open"
    """
    :func:`open` and :meth:`pathlib.Path.open`, unless they open the file in binary
    mode.
    """


class TextKeyword(StrEnum):
    """
    The keyword arguments that decide how a call reads and writes text.
    """

    ENCODING = "encoding"
    """
    The encoding text is read and written in.
    """

    MODE = "mode"
    """
    The mode :data:`TextFunction.OPEN` opens a file in.
    """

    TEXT = "text"
    """
    The :mod:`subprocess` switch decoding output in the locale encoding.
    """


BINARY_MODE = "b"
"""
The letter in a file mode that opens the file for bytes rather than text.
"""


# %% the check


@dataclass(frozen=True)
class LocaleEncodingChecker(CodeRuleChecker):
    """
    Finds calls reading or writing text without naming its encoding: file reads and
    writes, files opened in text mode, and :mod:`subprocess` calls decoding their output.
    """

    @override
    def violations(self, path: Path) -> Iterator[CodeRuleViolation]:
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if not isinstance(node, ast.Call) or not self.uses_locale_encoding(node):
                continue
            yield CodeRuleViolation(
                path,
                node.lineno,
                node.end_lineno,
                "reads or writes text in the locale encoding, which on Windows cannot "
                f'encode most of Unicode; pass {TextKeyword.ENCODING}="utf-8"',
            )

    def uses_locale_encoding(self, call: ast.Call) -> bool:
        """
        :return: Whether *call* reads or writes text without naming its encoding.
        """
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        if TextKeyword.ENCODING in keywords:
            return False
        if self.is_subprocess_call(call):
            switch = keywords.get(TextKeyword.TEXT)
            return isinstance(switch, ast.Constant) and switch.value is True
        function = call.func
        name = function.attr if isinstance(function, ast.Attribute) else None
        if isinstance(function, ast.Name):
            name = function.id
        if name == TextFunction.OPEN:
            return self.opens_a_file(call) and not self.opens_bytes(call, keywords)
        return name in (TextFunction.READ_TEXT, TextFunction.WRITE_TEXT)

    @staticmethod
    def is_subprocess_call(call: ast.Call) -> bool:
        """
        :return: Whether *call* calls a function of :mod:`subprocess`.
        """
        function = call.func
        return (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == subprocess.__name__
        )

    @staticmethod
    def opens_a_file(call: ast.Call) -> bool:
        """
        :return: Whether *call*, an :data:`TextFunction.OPEN`, opens a file: a call of
            :func:`open`, or a method call given nothing but a mode, as
            :meth:`pathlib.Path.open` is, unlike an opener handed a request.
        """
        if isinstance(call.func, ast.Name):
            return True
        return all(isinstance(argument, ast.Constant) for argument in call.args)

    @staticmethod
    def opens_bytes(call: ast.Call, keywords: dict[str | None, ast.expr]) -> bool:
        """
        :param keywords: The keyword arguments of *call*, by name.
        :return: Whether *call*, an :data:`TextFunction.OPEN`, names a binary mode: by
            keyword, as the second argument of :func:`open` or the first of
            :meth:`pathlib.Path.open`.
        """
        mode_position = 0 if isinstance(call.func, ast.Attribute) else 1
        mode = keywords.get(TextKeyword.MODE)
        if mode is None and len(call.args) > mode_position:
            mode = call.args[mode_position]
        return (
            isinstance(mode, ast.Constant)
            and isinstance(mode.value, str)
            and BINARY_MODE in mode.value
        )
