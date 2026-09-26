"""加热换向状态快照。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeatingSnapshot:
    """加热换向某一时刻的状态。"""

    waste_gas_open: bool
    gas_open: bool
    temperature_c: float
    confirmed: bool
    reversals: int
    seconds_to_due: float

    def as_dict(self) -> dict:
        return {
            "waste_gas_open": self.waste_gas_open,
            "gas_open": self.gas_open,
            "temperature_c": round(self.temperature_c, 2),
            "confirmed": self.confirmed,
            "reversals": self.reversals,
            "seconds_to_due": round(self.seconds_to_due, 2),
        }
