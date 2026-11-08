"""
A REST resource's own page on GitHub, and links GitHub may report as null.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from basstler.json_model import RawValueReader, ValidatedJSONModel

# %% links


class AbsentAsEmpty(RawValueReader):
    """
    Reads a text GitHub reports as null as empty text.
    """

    def read(self, value: str | None) -> str:
        return value or ""


class WebPage(ValidatedJSONModel):
    """
    A REST resource that has a page of its own on github.com.
    """

    page_url: Annotated[str, Field(alias="html_url")]
    """
    The address of its own page on GitHub.
    """
