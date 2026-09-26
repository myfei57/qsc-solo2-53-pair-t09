"""拦焦车。

拦焦车停在焦侧，负责把导焦栅对准炭化室并锁定，焦炭才能沿着导焦栅落到熄焦
车里。对齐与锁定是推焦的硬前置：不先对位、不先锁栅，推焦一律拒绝。
"""

from __future__ import annotations

from .align import Alignment
from .machine import GuideCar
from .snapshot import GuideSnapshot

__all__ = ["GuideCar", "GuideSnapshot", "Alignment"]
