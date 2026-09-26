"""拦焦车状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideSnapshot:
    """拦焦车某一时刻的状态。"""

    oven: str
    measured_mm: float
    deviation_mm: float
    tolerance_mm: float
    aligned: bool
    locked: bool
    apron_deg: float

    def as_dict(self) -> dict:
        return {
            "oven": self.oven,
            "measured_mm": round(self.measured_mm, 2),
            "deviation_mm": round(self.deviation_mm, 2),
            "tolerance_mm": round(self.tolerance_mm, 2),
            "aligned": self.aligned,
            "locked": self.locked,
            "apron_deg": round(self.apron_deg, 2),
        }
