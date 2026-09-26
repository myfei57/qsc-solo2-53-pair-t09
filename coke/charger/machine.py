"""装煤车状态机。

煤斗对位沿用"实测位置 / 目标位置 / 公差"口径；给煤按吨位与给煤速率推进，
装满目标吨位后停止。给煤必须在煤斗对位之后进行，未对位直接拒绝。
"""

from __future__ import annotations

from ..config import ChargerLimits
from ..errors import AlignmentError
from ..guide.align import Alignment
from .snapshot import ChargerSnapshot


class ChargingCar:
    """装煤车煤斗状态机。"""

    def __init__(self, limits: ChargerLimits) -> None:
        self._limits = limits
        self._oven = ""
        self._hopper_mm = 0.0
        self._deviation_mm = 0.0
        self._aligned = False
        self._coal_load_t = limits.coal_target_t
        self._fed_t = 0.0
        self._feeding = False

    @property
    def limits(self) -> ChargerLimits:
        return self._limits

    def align_hopper(self, oven: str, target_mm: float, measured_mm: float) -> Alignment:
        """核对煤斗对位，返回核对结果。"""

        alignment = Alignment(float(target_mm), float(measured_mm), self._limits.align_tolerance_mm)
        self._oven = oven
        self._hopper_mm = alignment.measured_mm
        self._deviation_mm = alignment.deviation_mm
        self._aligned = alignment.ok
        return alignment

    def is_aligned(self) -> bool:
        """煤斗是否已对位。"""

        return self._aligned

    def feed(self, dt: float) -> float:
        """按给煤速率推进一个步长，返回本次给煤吨位。"""

        if not self._aligned:
            raise AlignmentError("煤斗未对位，禁止给煤", component="charger")
        if dt <= 0:
            raise ValueError("步长必须为正")
        remaining = self._limits.coal_target_t - self._fed_t
        if remaining <= 0:
            self._feeding = False
            return 0.0
        amount = self._limits.feed_rate_t_per_min * dt / 60.0
        amount = min(amount, remaining)
        self._fed_t += amount
        self._feeding = self._fed_t < self._limits.coal_target_t
        if not self._feeding:
            self._coal_load_t = 0.0
        return amount

    def feed_complete(self) -> bool:
        """是否已达到目标装煤量。"""

        return self._fed_t >= self._limits.coal_target_t

    def snapshot(self) -> ChargerSnapshot:
        """返回装煤车状态快照。"""

        return ChargerSnapshot(
            oven=self._oven,
            hopper_measured_mm=self._hopper_mm,
            deviation_mm=self._deviation_mm,
            aligned=self._aligned,
            coal_load_t=self._coal_load_t,
            fed_t=self._fed_t,
            feeding=self._feeding,
        )
