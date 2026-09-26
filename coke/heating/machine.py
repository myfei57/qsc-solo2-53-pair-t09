"""换向排程。

按固定间隔判定是否到期；每次成功换向记录时间并累加计数。到期末打标记不会
自己换向，仍由编排在确认安全后调用，符合"申请 → 执行 → 确认"的真实节奏。
"""

from __future__ import annotations

from ..config import HeatingLimits
from ..clock import Clock


class HeatingReversal:
    """加热换向排程器。"""

    def __init__(self, limits: HeatingLimits, clock: Clock) -> None:
        self._limits = limits
        self._clock = clock
        self._last_ts = clock.now()
        self._count = 0

    @property
    def limits(self) -> HeatingLimits:
        return self._limits

    def due(self, now: float | None = None) -> bool:
        """当前时刻是否已到换向间隔。"""

        moment = self._clock.now() if now is None else now
        return (moment - self._last_ts) >= self._limits.reversal_interval_s

    def mark_reversed(self, now: float | None = None) -> int:
        """记录一次换向，返回累计换向次数。"""

        self._last_ts = self._clock.now() if now is None else now
        self._count += 1
        return self._count

    def count(self) -> int:
        """返回累计换向次数。"""

        return self._count

    def seconds_to_due(self, now: float | None = None) -> float:
        """返回距下次换向还有多少秒（已到期返回 0）。"""

        moment = self._clock.now() if now is None else now
        remaining = self._limits.reversal_interval_s - (moment - self._last_ts)
        return max(0.0, remaining)
