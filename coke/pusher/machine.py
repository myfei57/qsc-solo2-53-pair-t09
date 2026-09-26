"""推焦机状态机。

状态只在 ``idle``、``extending``（推焦杆前进）、``retracting``（退杆）之间
切换。行程不得超过配置的最大行程；一次完整"前进到目标 + 返回"记一次推焦
行程。推进是按 :meth:`advance` 显式驱动的，控制循环与验证环境都能按固定
步长观察杆位变化。
"""

from __future__ import annotations

from ..config import PusherLimits
from ..errors import InterlockError
from .snapshot import PusherSnapshot

IDLE = "idle"
EXTENDING = "extending"
RETRACTING = "retracting"


class PusherMachine:
    """推焦杆状态机。"""

    def __init__(self, limits: PusherLimits) -> None:
        self._limits = limits
        self._ram_mm = 0.0
        self._target_mm = 0.0
        self._state = IDLE
        self._committed_mm_s = limits.speed_default_mm_s
        self._strokes = 0

    @property
    def limits(self) -> PusherLimits:
        return self._limits

    @property
    def state(self) -> str:
        return self._state

    @property
    def ram_mm(self) -> float:
        return self._ram_mm

    def committed_speed(self) -> float:
        """返回当前提交给执行器的速度。"""

        return self._committed_mm_s

    def set_speed(self, speed_mm_s: float) -> float:
        """把仲裁后的速度提交给执行器，越界即夹到配置区间。"""

        clamped = max(self._limits.speed_min_mm_s, min(self._limits.speed_max_mm_s, float(speed_mm_s)))
        self._committed_mm_s = clamped
        return clamped

    def drive_to(self, target_mm: float, speed_mm_s: float | None = None) -> float:
        """下达推焦行程指令，返回生效的目标杆位。"""

        target = float(target_mm)
        if target <= self._ram_mm:
            raise InterlockError(
                f"推焦目标 {target} 必须大于当前杆位 {self._ram_mm}", component="pusher"
            )
        if target > self._limits.max_stroke_mm:
            raise InterlockError(
                f"推焦目标 {target} 超过最大行程 {self._limits.max_stroke_mm}", component="pusher"
            )
        if speed_mm_s is not None:
            self.set_speed(speed_mm_s)
        self._target_mm = target
        self._state = EXTENDING
        return target

    def retract(self) -> None:
        """下达退杆指令。"""

        self._target_mm = 0.0
        self._state = RETRACTING

    def advance(self, dt: float) -> bool:
        """按提交速度和步长推进杆位，返回本次是否到达目标。"""

        if self._state == IDLE:
            return True
        if dt <= 0:
            raise ValueError("步长必须为正")
        step = self._committed_mm_s * dt
        remaining = self._target_mm - self._ram_mm
        if abs(remaining) <= step:
            self._ram_mm = self._target_mm
            reached = True
        else:
            self._ram_mm += step if remaining > 0 else -step
            reached = False
        if reached:
            finished_forward = self._state == EXTENDING
            self._state = IDLE
            if finished_forward:
                self._strokes += 1
        return reached

    def at_target(self) -> bool:
        """是否停在目标杆位。"""

        return self._state == IDLE and abs(self._ram_mm - self._target_mm) < 1e-9

    def snapshot(self) -> PusherSnapshot:
        """返回推焦机状态快照。"""

        return PusherSnapshot(
            state=self._state,
            ram_mm=self._ram_mm,
            target_mm=self._target_mm,
            committed_mm_s=self._committed_mm_s,
            strokes=self._strokes,
        )
