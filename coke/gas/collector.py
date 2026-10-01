"""集气管压力状态。

压力需要被调节到目标带内才算"调好"，装煤序列据此放行桥管翻板。外部扰动
（开盖、换向）会临时把压力拉走，由控制循环周期性重新调节。
"""

from __future__ import annotations

from ..config import CollectorLimits
from .pressure import regulate_pressure


class CollectorMain:
    """集气管压力状态机。"""

    def __init__(self, limits: CollectorLimits, initial_pa: float = 30.0) -> None:
        self._limits = limits
        self._pressure_pa = float(initial_pa)

    @property
    def limits(self) -> CollectorLimits:
        return self._limits

    @property
    def pressure_pa(self) -> float:
        return self._pressure_pa

    def regulate(self, dt: float) -> float:
        """向目标压力调节一个步长，返回新压力。"""

        self._pressure_pa = regulate_pressure(
            self._pressure_pa,
            self._limits.pressure_target_pa,
            self._limits.regulate_rate_pa_per_s,
            dt,
        )
        return self._pressure_pa

    def disturb(self, delta_pa: float) -> float:
        """施加一次外部扰动，返回扰动后的压力。"""

        self._pressure_pa += float(delta_pa)
        return self._pressure_pa

    def restore(self, pressure_pa: float) -> float:
        """把压力直接恢复到给定值，返回恢复后的压力。

        只用于需求调度预调失败后的回退：压力放回调度记录里调压前的值，
        控制循环随后从原状态重新调节；正常调节走 ``regulate``。
        """

        self._pressure_pa = float(pressure_pa)
        return self._pressure_pa

    def settled(self) -> bool:
        """压力是否已进入目标带。"""

        return self._limits.settled(self._pressure_pa)
