"""炉门清扫机状态机。

清扫头只有在炉门打开、闩锁松开之后才能伸入；清扫进度按清扫时长累计，达到
设定时长即完成。清扫完成由编排把闩锁重新压紧，机内只记录是否清完。
"""

from __future__ import annotations

from ..config import DoorLimits
from ..errors import InterlockError
from .latch import DoorLatch


class DoorCleaner:
    """炉门清扫机。"""

    def __init__(self, limits: DoorLimits, latch: DoorLatch) -> None:
        self._limits = limits
        self._latch = latch
        self._oven = ""
        self._door_open = False
        self._elapsed_s = 0.0
        self._cleaned = False
        self._cycles = 0

    @property
    def limits(self) -> DoorLimits:
        return self._limits

    @property
    def latch(self) -> DoorLatch:
        return self._latch

    def open_door(self, oven: str) -> None:
        """打开炉门并记录碳化室号。"""

        self._oven = oven
        self._door_open = True
        self._elapsed_s = 0.0
        self._cleaned = False

    def clean(self, dt: float) -> float:
        """推进清扫一个步长，返回清扫进度（0–1）。"""

        if not self._door_open:
            raise InterlockError("炉门未打开，禁止清扫", component="door")
        if self._latch.is_engaged():
            raise InterlockError("炉门闩锁未松开，禁止清扫", component="door")
        if dt <= 0:
            raise ValueError("步长必须为正")
        self._elapsed_s += dt
        return self.progress()

    def close_door(self) -> None:
        """关闭炉门；清扫完成后由编排压紧闩锁。"""

        self._door_open = False
        if self._cleaned:
            self._latch.set_engaged()

    def progress(self) -> float:
        """返回清扫进度（0–1）。"""

        ratio = self._elapsed_s / self._limits.clean_duration_s
        return min(1.0, ratio)

    def mark_cleaned(self) -> int:
        """标记本炉清扫完成，返回累计清扫炉数。"""

        if self.progress() < 1.0:
            raise InterlockError("清扫未完成，不能标记完成", component="door")
        self._cleaned = True
        self._cycles += 1
        return self._cycles

    def is_cleaned(self) -> bool:
        """本炉是否已清扫完成。"""

        return self._cleaned

    def door_open(self) -> bool:
        """炉门是否打开。"""

        return self._door_open

    def snapshot(self):
        """返回炉门清扫状态快照。"""

        from .snapshot import DoorSnapshot

        return DoorSnapshot(
            oven=self._oven,
            door_open=self._door_open,
            latch_engaged=self._latch.is_engaged(),
            latch_position_mm=self._latch.position_mm,
            cleaned=self._cleaned,
            progress=self.progress(),
            cycles=self._cycles,
        )
