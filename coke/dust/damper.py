"""除尘挡板。"""

from __future__ import annotations


class DustDamper:
    """带开度与驱动速率的除尘挡板。"""

    def __init__(self, open_deg: float, rate_deg_per_s: float) -> None:
        self._open_deg = float(open_deg)
        self._rate_deg_per_s = float(rate_deg_per_s)
        self._angle_deg = 0.0

    @property
    def open_deg(self) -> float:
        return self._open_deg

    @property
    def angle_deg(self) -> float:
        return self._angle_deg

    def drive_to(self, target_deg: float, dt: float) -> float:
        """按驱动速率把挡板推向目标开度，返回新开度。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        target = max(0.0, min(90.0, float(target_deg)))
        step = self._rate_deg_per_s * dt
        delta = target - self._angle_deg
        if abs(delta) <= step:
            self._angle_deg = target
        else:
            self._angle_deg += step if delta > 0 else -step
        return self._angle_deg

    def at_open(self) -> bool:
        """挡板是否已开到工作开度。"""

        return self._angle_deg >= self._open_deg - 1e-9
