"""装煤车。

装煤车把煤斗送到炭化室顶部并对位，随后在集气管压力稳定、桥管翻板打开之后
给煤。煤斗对位是装煤的硬前置。
"""

from __future__ import annotations

from .machine import ChargingCar
from .snapshot import ChargerSnapshot

__all__ = ["ChargingCar", "ChargerSnapshot"]
