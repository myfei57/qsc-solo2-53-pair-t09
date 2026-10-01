"""集气管、桥管与装煤需求调度。

装煤前必须先把集气管压力调到目标带，再把桥管翻板打开放荒煤气；翻板闩锁防
止同一炉被重复开阀。多炉同时装煤时由需求调度层统一排队预调，避免几路各抢
各的把集气管压力顶偏、荒煤气倒灌。
"""

from __future__ import annotations

from .collector import CollectorMain
from .demand import DemandScheduler, DemandTicket, OvenCondition
from .flap import BridgeFlap
from .latch import FlapLatch
from .pressure import regulate_pressure
from .snapshot import GasSnapshot

__all__ = [
    "CollectorMain",
    "BridgeFlap",
    "FlapLatch",
    "regulate_pressure",
    "GasSnapshot",
    "OvenCondition",
    "DemandTicket",
    "DemandScheduler",
]
