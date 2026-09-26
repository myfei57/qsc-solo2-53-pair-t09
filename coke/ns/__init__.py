"""现场命名空间与工艺链拓扑。

命名空间把"区域.设备"映射到设备类型，控制台与审计共用同一套名字；拓扑描述
「装煤 → 加热 → 推焦 → 导焦 → 熄焦 → 除尘 → 审计」这条硬顺序链，用来在
操作前检查工位是否满足前一阶段已完成。
"""

from __future__ import annotations

from .registry import NamespaceRegistry
from .topology import STAGES, Topology, build_default_topology

__all__ = ["NamespaceRegistry", "Topology", "STAGES", "build_default_topology"]
