"""除尘。

除尘挡板随推焦联动：推焦一开始就按联动滞后把挡板开到工作开度，推焦结束后
回到停靠位。挡板行程带滞后，控制台能看出"推焦已开始、挡板还在开"的过渡。
"""

from __future__ import annotations

from .damper import DustDamper
from .schedule import DamperSchedule
from .snapshot import DustSnapshot
from .system import DustSystem

__all__ = ["DustSystem", "DustDamper", "DamperSchedule", "DustSnapshot"]
