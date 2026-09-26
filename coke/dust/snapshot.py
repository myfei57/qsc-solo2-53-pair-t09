"""除尘状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DustSnapshot:
    """除尘某一时刻的状态。"""

    fan_running: bool
    damper_deg: float
    damper_open: bool
    linkage_pending: bool
    links: int

    def as_dict(self) -> dict:
        return {
            "fan_running": self.fan_running,
            "damper_deg": round(self.damper_deg, 2),
            "damper_open": self.damper_open,
            "linkage_pending": self.linkage_pending,
            "links": self.links,
        }
