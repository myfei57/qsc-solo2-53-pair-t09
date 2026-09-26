"""炉门闩锁。

闩锁有压紧与松开两态：压紧时炉门密封、清扫头不能进入；松开时炉门可以开
清扫。闩锁行程按配置核对，超差即认为没有真正松开。
"""

from __future__ import annotations

from ..errors import InterlockError


class DoorLatch:
    """带行程核对的炉门闩锁。"""

    def __init__(self, travel_mm: float) -> None:
        self._travel_mm = float(travel_mm)
        self._engaged = True
        self._position_mm = float(travel_mm)
        self._cycles = 0

    @property
    def travel_mm(self) -> float:
        return self._travel_mm

    @property
    def position_mm(self) -> float:
        return self._position_mm

    def set_engaged(self) -> bool:
        """压紧闩锁，返回压紧状态。"""

        self._engaged = True
        self._position_mm = self._travel_mm
        self._cycles += 1
        return self._engaged

    def release(self, position_mm: float | None = None) -> bool:
        """松开闩锁，返回松开状态；行程不足即拒绝。"""

        measured = self._travel_mm if position_mm is None else float(position_mm)
        if measured < self._travel_mm:
            raise InterlockError(
                f"闩锁行程 {measured} 不足 {self._travel_mm}，未真正松开", component="door"
            )
        self._engaged = False
        self._position_mm = 0.0
        return self._engaged

    def is_engaged(self) -> bool:
        """闩锁是否处于压紧状态。"""

        return self._engaged

    def cycles(self) -> int:
        """返回闩锁压紧次数。"""

        return self._cycles
