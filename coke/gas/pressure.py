"""集气管压力调节律。

把当前压力按"每步最多变化 rate×dt"的斜率推向目标，避免一步到位把压力拉到
目标造成翻板冲刷。单纯的斜率限制可以显式复算，便于审计核对每一步的收敛。
"""

from __future__ import annotations


def regulate_pressure(
    current_pa: float, target_pa: float, rate_pa_per_s: float, dt: float
) -> float:
    """按斜率把压力推进一个步长，返回新压力。"""

    if dt <= 0:
        raise ValueError("步长必须为正")
    if rate_pa_per_s <= 0:
        raise ValueError("调节速率必须为正")
    delta = float(target_pa) - float(current_pa)
    step = rate_pa_per_s * dt
    if abs(delta) <= step:
        return float(target_pa)
    return float(current_pa) + (step if delta > 0 else -step)
