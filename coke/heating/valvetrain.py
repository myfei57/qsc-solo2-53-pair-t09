"""煤气／废气阀组。

两个阀互斥：关废气阀之后才能开煤气阀，关煤气阀之后才能开废气阀。任一步
在条件不满足时都被拒绝，避免两个阀同时开启造成串气。
"""

from __future__ import annotations

from ..errors import InterlockError


class ValveTrain:
    """煤气阀与废气阀（互斥）。"""

    def __init__(self) -> None:
        self._waste_open = True
        self._gas_open = False
        self._reversals = 0

    @property
    def waste_open(self) -> bool:
        return self._waste_open

    @property
    def gas_open(self) -> bool:
        return self._gas_open

    def close_waste_gas(self) -> bool:
        """关闭废气阀，返回关阀后的状态。"""

        self._waste_open = False
        return self._waste_open

    def open_gas(self) -> bool:
        """打开煤气阀；废气阀未关即拒绝。"""

        if self._waste_open:
            raise InterlockError("废气阀未关，禁止开煤气阀", component="heating")
        if self._gas_open:
            raise InterlockError("煤气阀已开，禁止重复打开", component="heating")
        self._gas_open = True
        self._reversals += 1
        return self._gas_open

    def close_gas(self) -> bool:
        """关闭煤气阀，返回关阀后的状态。"""

        self._gas_open = False
        return self._gas_open

    def open_waste_gas(self) -> bool:
        """打开废气阀；煤气阀未关即拒绝。"""

        if self._gas_open:
            raise InterlockError("煤气阀未关，禁止开废气阀", component="heating")
        self._waste_open = True
        return self._waste_open

    def reversals(self) -> int:
        """返回累计换向次数。"""

        return self._reversals
