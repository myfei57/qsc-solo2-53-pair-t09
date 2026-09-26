"""集气管与桥管状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GasSnapshot:
    """集气管某一时刻的状态。"""

    pressure_pa: float
    target_pa: float
    settled: bool
    flap_deg: float
    flap_open: bool
    latch_engaged: bool
    latch_cycles: int
    latch_resets: int

    def as_dict(self) -> dict:
        return {
            "pressure_pa": round(self.pressure_pa, 2),
            "target_pa": round(self.target_pa, 2),
            "settled": self.settled,
            "flap_deg": round(self.flap_deg, 2),
            "flap_open": self.flap_open,
            "latch_engaged": self.latch_engaged,
            "latch_cycles": self.latch_cycles,
            "latch_resets": self.latch_resets,
        }
