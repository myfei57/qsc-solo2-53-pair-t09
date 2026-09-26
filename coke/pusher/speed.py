"""推焦速度仲裁。

自动循环与手动控制台会同时向推焦杆提交速度。仲裁按优先级取最高的一路；优先
级相同则取最新提交。仲裁结果是唯一提交值，执行器永远只看到一个速度，避免
抢指令把推焦杆抖成两段动作。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeedOutcome:
    """一次仲裁结果。"""

    winner: str
    speed_mm_s: float
    priority: int
    contenders: int

    def as_dict(self) -> dict:
        return {
            "winner": self.winner,
            "speed_mm_s": round(self.speed_mm_s, 2),
            "priority": self.priority,
            "contenders": self.contenders,
        }


class SpeedArbiter:
    """按优先级与提交时序仲裁推焦速度。"""

    def __init__(self, min_mm_s: float, max_mm_s: float, default_mm_s: float) -> None:
        self._min = float(min_mm_s)
        self._max = float(max_mm_s)
        self._committed = float(default_mm_s)
        self._seq = 0
        self._requests: dict[str, tuple[float, int, int]] = {}

    @property
    def limits(self) -> tuple[float, float]:
        return (self._min, self._max)

    def request(self, writer: str, speed_mm_s: float, priority: int) -> None:
        """登记一路速度请求（最高优先级 + 最新提交胜出）。"""

        self._seq += 1
        clamped = max(self._min, min(self._max, float(speed_mm_s)))
        self._requests[writer] = (clamped, int(priority), self._seq)

    def resolve(self) -> SpeedOutcome:
        """收敛所有请求，返回并记录唯一提交值。"""

        if not self._requests:
            return SpeedOutcome("none", self._committed, 0, 0)
        winner, (speed, priority, _seq) = max(
            self._requests.items(), key=lambda item: (item[1][1], item[1][2])
        )
        self._committed = speed
        return SpeedOutcome(winner, speed, priority, len(self._requests))

    def committed(self) -> float:
        """返回最近一次提交速度。"""

        return self._committed

    def writers(self) -> list[str]:
        """返回当前登记了请求的写入方。"""

        return sorted(self._requests)
