"""炉温确认。

换向后要拿炉温回读确认：只有落在目标带内才算换向成功，否则本次换向记为
未确认并写审计。温度由现场采样喂入，控制器只负责判定。
"""

from __future__ import annotations

from ..config import HeatingLimits


class OvenTemperature:
    """炉温回读与确认。"""

    def __init__(self, limits: HeatingLimits, initial_c: float | None = None) -> None:
        self._limits = limits
        self._value_c = float(initial_c if initial_c is not None else limits.temp_target_c)

    @property
    def limits(self) -> HeatingLimits:
        return self._limits

    @property
    def value_c(self) -> float:
        return self._value_c

    def update(self, temperature_c: float) -> float:
        """喂入一次炉温回读，返回新温度。"""

        self._value_c = float(temperature_c)
        return self._value_c

    def confirmed(self) -> bool:
        """炉温是否落在确认带内。"""

        return self._limits.confirmed(self._value_c)

    def offset_c(self) -> float:
        """返回与目标温度的偏差。"""

        return self._value_c - self._limits.temp_target_c
