"""集气管与桥管。

装煤前必须先把集气管压力调到目标带，再把桥管翻板打开放荒煤气；翻板闩锁防
止同一炉被重复开阀。压力、翻板、闩锁三者共同构成"先调压、后开翻板"的硬
顺序。
"""

from __future__ import annotations

from .collector import CollectorMain
from .flap import BridgeFlap
from .latch import FlapLatch
from .pressure import regulate_pressure
from .snapshot import GasSnapshot

__all__ = ["CollectorMain", "BridgeFlap", "FlapLatch", "regulate_pressure", "GasSnapshot"]
