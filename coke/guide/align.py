"""导焦栅对齐计算。

对齐就是比较实测位置与目标位置的偏差是否落在公差内。把它单独成类型，
是因为拦焦车、装煤车煤斗和推焦杆都要用同一套"偏差 + 公差"的口径。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Alignment:
    """一次对齐核对结果。"""

    target_mm: float
    measured_mm: float
    tolerance_mm: float

    @property
    def deviation_mm(self) -> float:
        return self.measured_mm - self.target_mm

    @property
    def ok(self) -> bool:
        """偏差是否落在公差内。"""

        return abs(self.deviation_mm) <= self.tolerance_mm

    def as_dict(self) -> dict:
        return {
            "target_mm": round(self.target_mm, 2),
            "measured_mm": round(self.measured_mm, 2),
            "deviation_mm": round(self.deviation_mm, 2),
            "tolerance_mm": round(self.tolerance_mm, 2),
            "ok": self.ok,
        }
