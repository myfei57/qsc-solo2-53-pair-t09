"""熄焦车状态机。

接焦只在焦侧进行；接焦之后才能走行，走行到位之后才能开喷淋。喷淋阈前检查
避免了"没走行到位就喷淋"这类会把红焦留在轨道上的顺序错误。
"""

from __future__ import annotations

from ..config import QuenchLimits
from ..errors import InterlockError
from .snapshot import QuenchSnapshot
from .spray import Spray
from .travel import TravelPlan


class QuenchCar:
    """熄焦车状态机。"""

    def __init__(self, limits: QuenchLimits) -> None:
        self._limits = limits
        self._plan = TravelPlan(limits.travel_distance_m, limits.travel_speed_m_s)
        self._spray = Spray(limits.spray_duration_s, limits.water_flow_m3_h)
        self._oven = ""
        self._loaded = False
        self._travelled_m = 0.0

    @property
    def plan(self) -> TravelPlan:
        return self._plan

    @property
    def spray(self) -> Spray:
        return self._spray

    def receive(self, oven: str) -> None:
        """在焦侧接焦。"""

        self.reset()
        self._oven = oven
        self._loaded = True

    def travel(self, dt: float) -> float:
        """走行到熄焦塔，返回新的已走行距离。"""

        if not self._loaded:
            raise InterlockError("熄焦车未接焦，禁止走行", component="quench")
        self._travelled_m = self._plan.step(self._travelled_m, dt)
        if self.at_tower():
            self._loaded = False
        return self._travelled_m

    def at_tower(self) -> bool:
        """是否已走行到熄焦塔。"""

        return self._travelled_m >= self._plan.distance_m

    def start_spray(self) -> None:
        """开喷淋；未走行到位或已喷淋过即拒绝。"""

        if not self.at_tower():
            raise InterlockError("熄焦车未走行到位，禁止喷淋", component="quench")
        if self._spray.complete():
            raise InterlockError("本炉已喷淋完成，禁止重复喷淋", component="quench")
        self._spray.open_valve()

    def spray_step(self, dt: float) -> float:
        """按步长推进喷淋，返回本次喷水量。"""

        return self._spray.step(dt)

    def reset(self) -> None:
        """复位走行与喷淋，准备下一炉（接焦时自动调用）。"""

        self._loaded = False
        self._travelled_m = 0.0
        self._spray = Spray(self._limits.spray_duration_s, self._limits.water_flow_m3_h)

    def snapshot(self) -> QuenchSnapshot:
        """返回熄焦车状态快照。"""

        return QuenchSnapshot(
            oven=self._oven,
            loaded=self._loaded,
            travelled_m=self._travelled_m,
            distance_m=self._plan.distance_m,
            at_tower=self.at_tower(),
            spraying=self._spray.open,
            spray_complete=self._spray.complete(),
            water_m3=self._spray.water_m3(),
        )
