"""工艺链拓扑。

控制链是「装煤 → 加热 → 推焦 → 导焦 → 熄焦 → 除尘 → 审计」，每一步都依赖
前一步在碳化室上完成。:class:`Topology` 保存这条依赖链，操作前用
``verify`` 检查某个阶段的前驱是否都已完成，未完成即返回缺失项（由调用方
决定是拒绝还是记录告警）。
"""

from __future__ import annotations

from dataclasses import dataclass

STAGES: tuple[str, ...] = (
    "charge",
    "heat",
    "push",
    "guide",
    "quench",
    "dust",
    "audit",
)


@dataclass(frozen=True)
class Stage:
    """一个工艺阶段及其前置阶段。"""

    name: str
    label: str
    requires: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "requires": list(self.requires)}


class Topology:
    """阶段依赖链。"""

    def __init__(self, stages: tuple[Stage, ...]) -> None:
        self._stages = stages
        self._index = {stage.name: stage for stage in stages}

    def stage(self, name: str) -> Stage:
        """按名字取阶段，不存在时抛出 ``KeyError``。"""

        return self._index[name]

    def order(self) -> list[str]:
        """返回阶段顺序。"""

        return [stage.name for stage in self._stages]

    def predecessors(self, name: str) -> tuple[str, ...]:
        """返回某阶段的直接前置阶段。"""

        return self.stage(name).requires

    def verify(self, completed: set[str]) -> dict:
        """检查每个阶段的直接前置是否都已完成。"""

        missing: dict[str, list[str]] = {}
        for stage in self._stages:
            gaps = [item for item in self.predecessors(stage.name) if item not in completed]
            if gaps:
                missing[stage.name] = gaps
        return {"ok": not missing, "missing": missing, "completed": sorted(completed)}

    def summary(self) -> dict:
        """汇总拓扑，供状态快照与控制台读取。"""

        return {"order": self.order(), "stages": [stage.as_dict() for stage in self._stages]}


def build_default_topology() -> Topology:
    """构造默认的工艺链拓扑。"""

    return Topology(
        (
            Stage("charge", "装煤", ()),
            Stage("heat", "加热", ("charge",)),
            Stage("push", "推焦", ("heat",)),
            Stage("guide", "导焦", ("push",)),
            Stage("quench", "熄焦", ("guide",)),
            Stage("dust", "除尘", ("quench",)),
            Stage("audit", "审计", ("dust",)),
        )
    )
