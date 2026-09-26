"""熄焦车状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuenchSnapshot:
    """熄焦车某一时刻的状态。"""

    oven: str
    loaded: bool
    travelled_m: float
    distance_m: float
    at_tower: bool
    spraying: bool
    spray_complete: bool
    water_m3: float

    def as_dict(self) -> dict:
        return {
            "oven": self.oven,
            "loaded": self.loaded,
            "travelled_m": round(self.travelled_m, 2),
            "distance_m": round(self.distance_m, 2),
            "at_tower": self.at_tower,
            "spraying": self.spraying,
            "spray_complete": self.spray_complete,
            "water_m3": round(self.water_m3, 3),
        }
