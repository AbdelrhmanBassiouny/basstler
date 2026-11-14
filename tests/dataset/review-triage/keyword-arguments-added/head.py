from __future__ import annotations

from dataclasses import dataclass


def scale(value: float, factor: float) -> float:
    return value * factor


@dataclass
class Point:
    x: float
    y: float


class Shape:
    def __init__(self, origin: Point) -> None:
        self.origin = origin

    def moved(self, offset: Point) -> Point:
        return Point(x=self.origin.x + offset.x, y=self.origin.y + offset.y)


class Square(Shape):
    def __init__(self, origin: Point, side: float) -> None:
        super().__init__(origin=origin)
        self.side = scale(value=side, factor=2.0)

    def corner(self) -> Point:
        return self.moved(offset=Point(x=self.side, y=self.side))
