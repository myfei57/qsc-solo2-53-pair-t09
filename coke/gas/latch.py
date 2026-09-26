"""桥管翻板闩锁。

翻板打开后会置位闩锁；同一炉在闩锁复位前不允许再次打开，避免重复开阀把
荒煤气倒灌进炭化室。闩锁按炉复位，复位动作与开阀动作都写审计。
"""

from __future__ import annotations


class FlapLatch:
    """桥管翻板的开阀闩锁。"""

    def __init__(self) -> None:
        self._engaged = False
        self._cycles = 0
        self._resets = 0

    def engage(self) -> bool:
        """置位闩锁，返回置位后的状态。"""

        self._engaged = True
        self._cycles += 1
        return self._engaged

    def reset(self) -> bool:
        """复位闩锁，返回复位后的状态。"""

        self._engaged = False
        self._resets += 1
        return self._engaged

    def is_engaged(self) -> bool:
        """闩锁是否处于置位状态。"""

        return self._engaged

    def cycles(self) -> int:
        """返回闩锁置位次数。"""

        return self._cycles

    def resets(self) -> int:
        """返回闩锁复位次数。"""

        return self._resets
