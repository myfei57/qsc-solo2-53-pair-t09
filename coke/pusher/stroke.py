"""推焦行程基线。

炭化室全长对应的推焦行程要按基线核对：推过头会把焦炭顶到炭化室尽头，推不
到位则残留焦炭。基线可重新标定（检修后），每次核对给出偏差与是否落在公差
内，供编排决定是否放行推焦。
"""

from __future__ import annotations


class StrokeBaseline:
    """带公差的推焦行程基线。"""

    def __init__(self, baseline_mm: float, tolerance_mm: float) -> None:
        if baseline_mm <= 0:
            raise ValueError("行程基线必须为正")
        self._baseline_mm = float(baseline_mm)
        self._tolerance_mm = float(tolerance_mm)
        self._epoch = 0

    @property
    def baseline_mm(self) -> float:
        return self._baseline_mm

    @property
    def tolerance_mm(self) -> float:
        return self._tolerance_mm

    @property
    def epoch(self) -> int:
        """返回基线代际，重新标定一次加一。"""

        return self._epoch

    def calibrate(self, value_mm: float) -> float:
        """重新标定基线，返回新的基线值。"""

        if value_mm <= 0:
            raise ValueError("标定值必须为正")
        self._baseline_mm = float(value_mm)
        self._epoch += 1
        return self._baseline_mm

    def check(self, position_mm: float) -> dict:
        """核对杆位与基线的偏差。"""

        deviation = float(position_mm) - self._baseline_mm
        return {
            "baseline_mm": round(self._baseline_mm, 2),
            "position_mm": round(float(position_mm), 2),
            "deviation_mm": round(deviation, 2),
            "tolerance_mm": round(self._tolerance_mm, 2),
            "epoch": self._epoch,
            "ok": abs(deviation) <= self._tolerance_mm,
        }
