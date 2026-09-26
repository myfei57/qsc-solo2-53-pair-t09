"""熄焦车。

熄焦车在焦侧接住整炉焦炭，先走行到熄焦塔下方，再喷淋降温。喷淋在水未落位
之前绝不能开：没走行到位就喷淋会把红焦留在轨道上。
"""

from __future__ import annotations

from .machine import QuenchCar
from .snapshot import QuenchSnapshot
from .spray import Spray
from .travel import TravelPlan

__all__ = ["QuenchCar", "QuenchSnapshot", "Spray", "TravelPlan"]
