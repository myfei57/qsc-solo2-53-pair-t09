"""装煤需求调度快照。

控制台展示调度结果用：当前仲裁模式（按此刻炉况与压力预演）、按仲裁规则排好
的等待队列、持有集气管授权的需求、各状态计数与最近的调度流水。快照里的队列
顺序与调度器实际授权顺序用同一套排序逻辑，保证"看到的"就是"会发生的"。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DispatchSnapshot:
    """调度器某一时刻的状态。"""

    mode: str
    mode_reason: str
    queued: tuple
    active: dict | None
    state_counts: dict
    recent: tuple
    records_total: int

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "mode_reason": self.mode_reason,
            "queued": list(self.queued),
            "active": self.active,
            "state_counts": dict(self.state_counts),
            "recent": list(self.recent),
            "records_total": self.records_total,
        }
