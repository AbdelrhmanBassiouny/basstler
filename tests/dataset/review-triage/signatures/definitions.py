from __future__ import annotations

from dataclasses import KW_ONLY, dataclass, field
from typing import ClassVar


@dataclass
class Base:
    identifier: int
    registry: ClassVar[dict] = {}


@dataclass
class Derived(Base):
    label: str
    cache: dict = field(default_factory=dict, init=False)
    _: KW_ONLY
    verbose: bool = False


class Plain:
    def __init__(self, first: int, /, second: int) -> None:
        self.total = first + second


class Inheriting(Plain):
    pass


class Collector:
    def gather(self, *items: int) -> list[int]:
        return list(items)

    @staticmethod
    def combine(left: int, right: int) -> int:
        return left + right

    @property
    def size(self) -> int:
        return 0


class Reader:
    def read(self, path: str) -> str:
        return path


class FastReader(Reader):
    def open(self, path: str) -> str:
        return self.read(path)


class Parser:
    def read(self, text: str, strict: bool) -> str:
        return text
