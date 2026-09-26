"""炉门清扫状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DoorSnapshot:
    """炉门清扫某一时刻的状态。"""

    oven: str
    door_open: bool
    latch_engaged: bool
    latch_position_mm: float
    cleaned: bool
    progress: float
    cycles: int

    def as_dict(self) -> dict:
        return {
            "oven": self.oven,
            "door_open": self.door_open,
            "latch_engaged": self.latch_engaged,
            "latch_position_mm": round(self.latch_position_mm, 2),
            "cleaned": self.cleaned,
            "progress": round(self.progress, 3),
            "cycles": self.cycles,
        }
