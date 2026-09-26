"""除尘系统运行状态。"""

from __future__ import annotations


class DustSystem:
    """除尘风机与开关状态。"""

    def __init__(self) -> None:
        self._running = False
        self._starts = 0

    def start(self) -> bool:
        """启动除尘风机，返回运行状态。"""

        if not self._running:
            self._starts += 1
        self._running = True
        return self._running

    def stop(self) -> bool:
        """停止除尘风机，返回运行状态。"""

        self._running = False
        return self._running

    def is_running(self) -> bool:
        """风机是否运行中。"""

        return self._running

    def starts(self) -> int:
        """返回累计启动次数。"""

        return self._starts
