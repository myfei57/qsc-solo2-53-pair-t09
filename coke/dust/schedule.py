"""除尘挡板联动时序。

推焦与挡板动作之间有固定滞后：从推焦开始时刻算起，滞后时间到才认为挡板应
该已经到位。调度器只回答"到没到联动时刻"，开度由挡板自己驱动。
"""

from __future__ import annotations


class DamperSchedule:
    """推焦联动的滞后调度。"""

    def __init__(self, lag_s: float) -> None:
        self._lag_s = float(lag_s)
        self._push_ts: float | None = None
        self._links = 0

    @property
    def lag_s(self) -> float:
        return self._lag_s

    def start_link(self, push_ts: float) -> None:
        """记录推焦开始时刻，启动一次联动。"""

        self._push_ts = float(push_ts)
        self._links += 1

    def due(self, now: float) -> bool:
        """联动滞后是否已到。"""

        if self._push_ts is None:
            return False
        return (float(now) - self._push_ts) >= self._lag_s

    def elapsed_s(self, now: float) -> float:
        """返回距推焦开始已经过去的秒数。"""

        if self._push_ts is None:
            return 0.0
        return max(0.0, float(now) - self._push_ts)

    def clear(self) -> None:
        """结束本次联动。"""

        self._push_ts = None

    def links(self) -> int:
        """返回累计联动次数。"""

        return self._links
