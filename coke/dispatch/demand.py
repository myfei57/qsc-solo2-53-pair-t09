"""装煤调度需求。

一座炭化室同一时刻只允许一条未完结需求（炉号即提交的幂等键）。需求状态机：

    queued ──仲裁授权+预调──▶ applied ──装煤完成──▶ released
                      │           │
                      │           └──失败/取消──▶ rolled_back（压力回退到调压前的值）
                      └──预调未到位──▶ partial ──回退──▶ rolled_back

``applied`` / ``partial`` 表示预调已占用集气管这条单资源，全炉组同一时刻只允许
一路；``released`` / ``rolled_back`` 是终态，终态后同炉才能提交下一条需求。
"""

from __future__ import annotations

from dataclasses import dataclass

DEMAND_STATES: tuple[str, ...] = ("queued", "applied", "partial", "released", "rolled_back")
"""需求的全部状态。"""

ACTIVE_STATES: tuple[str, ...] = ("applied", "partial")
"""持有集气管授权的状态（释放或回退前不允许调度下一路）。"""

TERMINAL_STATES: tuple[str, ...] = ("released", "rolled_back")
"""终态：需求已完结，同炉可再提交。"""


@dataclass
class ChargeDemand:
    """一路装煤需求及其授权决策。"""

    demand_id: str
    oven: str
    stage: str
    submit_seq: int
    submit_ts: float
    state: str = "queued"
    priority: int = 0
    mode: str = ""
    mode_reason: str = ""
    decided_ts: float = 0.0
    pressure_before_pa: float = 0.0
    prereg_target_pa: float = 0.0
    pressure_after_pa: float = 0.0
    decision_record: dict | None = None
    terminal_record: dict | None = None

    def wait_s(self, now: float) -> float:
        """返回从提交到 ``now`` 已等待的秒数。"""

        return max(0.0, float(now) - self.submit_ts)
