"""
Line numbers and line counts within the Python snippets the code rule checkers read.
"""

from __future__ import annotations

# %% where reported code starts

MODULE_FIRST_LINE = 1
"""
The line a module, and so its docstring, starts on.
"""

UNDOCUMENTED_FIELD_LINE = 32
"""
The line of the undocumented field in
:attr:`~tests.constants.paths.DocstringSnippet.UNDOCUMENTED_DEFINITIONS`.
"""

UNDOCUMENTED_METHOD_LINE = 38
"""
The line of the undocumented method in
:attr:`~tests.constants.paths.DocstringSnippet.UNDOCUMENTED_DEFINITIONS`.
"""

OVERLONG_ATTRIBUTE_DOCSTRING_LINE = 10
"""
The first line of the overlong docstring in
:attr:`~tests.constants.paths.ProseSnippet.OVERLONG_ATTRIBUTE_DOCSTRING`.
"""

LONG_COMMENT_BLOCK_LINE = 10
"""
The first line of the four-line comment block in
:attr:`~tests.constants.paths.ProseSnippet.COMMENT_BLOCKS`.
"""

# %% how long the prose is

FIELDS_AND_LITERAL_BLOCKS_PROSE_LINES = 2
"""
The prose lines of the docstring in
:attr:`~tests.constants.paths.ProseSnippet.FIELDS_AND_LITERAL_BLOCKS`.
"""

OVERLONG_MODULE_DOCSTRING_PROSE_LINES = 5
"""
The prose lines of the docstring in
:attr:`~tests.constants.paths.ProseSnippet.OVERLONG_MODULE_DOCSTRING`.
"""
