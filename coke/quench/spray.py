"""熄焦喷淋。

喷淋按时长累计：开阀后按流量与步长累加喷水量，累计时长达到设定值即完成。
喷淋只能在走行到位后开启（由编排保证），喷淋期间回读喷水量供审计核对。
"""

from __future__ import annotations

from ..errors import InterlockError


class Spray:
    """熄焦喷淋控制器。"""

    def __init__(self, duration_s: float, water_flow_m3_h: float) -> None:
        self._duration_s = float(duration_s)
        self._water_flow_m3_h = float(water_flow_m3_h)
        self._elapsed_s = 0.0
        self._water_m3 = 0.0
        self._open = False

    @property
    def duration_s(self) -> float:
        return self._duration_s

    @property
    def water_flow_m3_h(self) -> float:
        return self._water_flow_m3_h

    @property
    def open(self) -> bool:
        return self._open

    def open_valve(self) -> None:
        """开喷淋阀。"""

        self._open = True

    def close_valve(self) -> None:
        """关喷淋阀。"""

        self._open = False

    def step(self, dt: float) -> float:
        """按步长累加喷淋量与时长，返回本次喷水量。"""

        if not self._open:
            raise InterlockError("喷淋阀未开，无法喷淋", component="quench")
        if dt <= 0:
            raise ValueError("步长必须为正")
        amount = self._water_flow_m3_h * dt / 3600.0
        self._elapsed_s += dt
        self._water_m3 += amount
        if self._elapsed_s >= self._duration_s:
            self.close_valve()
        return amount

    def complete(self) -> bool:
        """喷淋是否达到设定时长。"""

        return self._elapsed_s >= self._duration_s

    def water_m3(self) -> float:
        """返回累计喷水量。"""

        return self._water_m3
