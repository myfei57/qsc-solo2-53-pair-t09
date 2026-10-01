"""装煤需求优先级。

定死：优先级**不按炉号固定**，按炉况动态算——炉号只是标识，同一座炉在结焦
初期（荒煤气发生量高峰、最容易把集气管压力顶偏）和结焦末期的调度紧迫度完全
不同。动态公式本身定死、可复算：

    priority = STAGE_WEIGHT[stage] + aging_bonus
    aging_bonus = min(int(wait_s // aging_step_s), aging_max_bonus)

结焦阶段权重 early=300 / mid=200 / late=100；等待每满一个老化步长加 1 分，
加分封顶，防止长等待需求被高优先级需求无限饿死。每条调度记录都带有炉况阶段、
提交时刻与决策时刻，巡检时能用同一公式复算出当时的优先级，审计口径一致。
"""

from __future__ import annotations

STAGES: tuple[str, ...] = ("early", "mid", "late")
"""结焦阶段：early=初期（煤气发生量高峰），mid=中期，late=末期。"""

STAGE_WEIGHT: dict[str, int] = {"early": 300, "mid": 200, "late": 100}
"""各结焦阶段的基础权重（定死，不随配置变化）。"""


def priority_of(stage: str, wait_s: float, aging_step_s: float, aging_max_bonus: int) -> int:
    """按炉况与等待时长计算优先级，数值越大越优先。"""

    if stage not in STAGE_WEIGHT:
        raise ValueError(f"未知结焦阶段 {stage!r}")
    if aging_step_s <= 0:
        raise ValueError("老化步长必须为正")
    aging = min(int(max(0.0, float(wait_s)) // aging_step_s), int(aging_max_bonus))
    return STAGE_WEIGHT[stage] + aging
