"""装煤车状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChargerSnapshot:
    """装煤车某一时刻的状态。"""

    oven: str
    hopper_measured_mm: float
    deviation_mm: float
    aligned: bool
    coal_load_t: float
    fed_t: float
    feeding: bool

    def as_dict(self) -> dict:
        return {
            "oven": self.oven,
            "hopper_measured_mm": round(self.hopper_measured_mm, 2),
            "deviation_mm": round(self.deviation_mm, 2),
            "aligned": self.aligned,
            "coal_load_t": round(self.coal_load_t, 3),
            "fed_t": round(self.fed_t, 3),
            "feeding": self.feeding,
        }
