"""装煤需求调度。

多座炭化室同时装煤时在现有调压律之上加一层需求调度：给同时在装的炉子按
炉况排优先级，冲突时按炉况选"先到先得"或"优先级插队"，授权后提前把集气管
压力往目标带预调，避免几路各抢各的把压力顶偏。预调幂等且可回退，调度记录
落流水并转发审计。
"""

from __future__ import annotations

from .demand import ChargeDemand
from .priority import priority_of
from .scheduler import DemandScheduler
from .snapshot import DispatchSnapshot

__all__ = ["ChargeDemand", "DemandScheduler", "DispatchSnapshot", "priority_of"]
