"""熄焦车走行计划。"""

from __future__ import annotations


class TravelPlan:
    """从焦侧到熄焦塔的走行距离与速度。"""

    def __init__(self, distance_m: float, speed_m_s: float) -> None:
        if distance_m <= 0 or speed_m_s <= 0:
            raise ValueError("走行距离与速度必须为正")
        self._distance_m = float(distance_m)
        self._speed_m_s = float(speed_m_s)

    @property
    def distance_m(self) -> float:
        return self._distance_m

    @property
    def speed_m_s(self) -> float:
        return self._speed_m_s

    def eta_s(self) -> float:
        """走完全程所需的时间。"""

        return self._distance_m / self._speed_m_s

    def step(self, travelled_m: float, dt: float) -> float:
        """按速度推进走行，返回新的已走行距离（不超过全程）。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        return min(self._distance_m, travelled_m + self._speed_m_s * dt)
