"""拦焦车状态机。

``align`` 记录一次对位结果（偏离公差则不算对好位），``lock_apron`` 在未对位
时直接抛出 :class:`InterlockError`。导焦栅锁定时角度抬到工作角，解锁时回到
停靠角。
"""

from __future__ import annotations

from ..config import GuideLimits
from ..errors import AlignmentError
from .align import Alignment
from .snapshot import GuideSnapshot

APRON_WORK_DEG = 88.0
APRON_PARK_DEG = 0.0


class GuideCar:
    """拦焦车导焦栅状态机。"""

    def __init__(self, limits: GuideLimits) -> None:
        self._limits = limits
        self._oven = ""
        self._measured_mm = 0.0
        self._deviation_mm = 0.0
        self._aligned = False
        self._locked = False
        self._apron_deg = APRON_PARK_DEG

    @property
    def limits(self) -> GuideLimits:
        return self._limits

    def align(self, oven: str, target_mm: float, measured_mm: float) -> Alignment:
        """按目标与实测位置核对对齐，返回核对结果。"""

        alignment = Alignment(float(target_mm), float(measured_mm), self._limits.align_tolerance_mm)
        self._oven = oven
        self._measured_mm = alignment.measured_mm
        self._deviation_mm = alignment.deviation_mm
        self._aligned = alignment.ok
        return alignment

    def is_aligned(self) -> bool:
        """导焦栅是否已对位。"""

        return self._aligned

    def align_tolerance(self) -> float:
        """返回对齐公差。"""

        return self._limits.align_tolerance_mm

    def lock_apron(self) -> float:
        """锁定导焦栅，返回锁定后的角度。"""

        if not self._aligned:
            raise AlignmentError("导焦栅未对位，禁止锁定", component="guide")
        self._locked = True
        self._apron_deg = APRON_WORK_DEG
        return self._apron_deg

    def unlock_apron(self) -> float:
        """解锁导焦栅，返回停靠角度。"""

        self._locked = False
        self._apron_deg = APRON_PARK_DEG
        return self._apron_deg

    def is_locked(self) -> bool:
        """导焦栅是否已锁定。"""

        return self._locked

    def reset(self) -> None:
        """回到未对位、未锁定的初始状态。"""

        self._aligned = False
        self._locked = False
        self._apron_deg = APRON_PARK_DEG

    def snapshot(self) -> GuideSnapshot:
        """返回拦焦车状态快照。"""

        return GuideSnapshot(
            oven=self._oven,
            measured_mm=self._measured_mm,
            deviation_mm=self._deviation_mm,
            tolerance_mm=self._limits.align_tolerance_mm,
            aligned=self._aligned,
            locked=self._locked,
            apron_deg=self._apron_deg,
        )
