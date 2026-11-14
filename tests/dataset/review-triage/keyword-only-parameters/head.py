from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Interval:
    lower: float
    upper: float


@dataclass(kw_only=True)
class Sample:
    value: float


def clamp(value: float, *, interval: Interval, strict: bool = False) -> float:
    return min(max(value, interval.lower), interval.upper)
