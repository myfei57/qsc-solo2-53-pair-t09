"""桥管翻板。

翻板打开前会检查闩锁：闩锁已置位说明本炉已经开过阀，重复打开直接拒绝。
打开后翻板抬起并置位闩锁；关闭只把翻板放下，闩锁要由编排显式复位。
"""

from __future__ import annotations

from ..errors import InterlockError
from .latch import FlapLatch

FLAP_OPEN_DEG = 85.0
FLAP_CLOSED_DEG = 0.0


class BridgeFlap:
    """桥管翻板状态机（自带开阀闩锁）。"""

    def __init__(self, latch: FlapLatch | None = None) -> None:
        self._latch = latch or FlapLatch()
        self._angle_deg = FLAP_CLOSED_DEG

    @property
    def latch(self) -> FlapLatch:
        return self._latch

    @property
    def angle_deg(self) -> float:
        return self._angle_deg

    def open(self) -> float:
        """打开翻板，返回开度；闩锁未复位即拒绝。"""

        if self._latch.is_engaged():
            raise InterlockError("翻板闩锁未复位，禁止重复打开", component="gas")
        self._angle_deg = FLAP_OPEN_DEG
        self._latch.engage()
        return self._angle_deg

    def close(self) -> float:
        """关闭翻板，返回停靠开度。"""

        self._angle_deg = FLAP_CLOSED_DEG
        return self._angle_deg

    def is_open(self) -> bool:
        """翻板是否处于打开状态。"""

        return self._angle_deg >= FLAP_OPEN_DEG - 1e-9

    def reset_latch(self) -> bool:
        """复位开阀闩锁，返回复位后的闩锁状态。"""

        return self._latch.reset()
