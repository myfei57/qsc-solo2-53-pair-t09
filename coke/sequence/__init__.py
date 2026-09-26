"""跨组件操作编排。

每个操作都是真实的跨模块调用链，顺序在编排里写死：装煤按"煤斗对位 →
集气管调压 → 开桥管翻板 → 给煤"，推焦按"导焦栅对位 → 锁定导焦栅 → 推焦 →
接焦"，换向按"废气阀 → 煤气阀 → 炉温确认"。顺序被破坏时返回 violations，
由平台写审计。
"""

from __future__ import annotations

from .charging import charge_oven
from .cleaning import clean_door
from .pushing import push_oven
from .quenching import quench_oven
from .reversal import reverse_heating

__all__ = ["charge_oven", "push_oven", "quench_oven", "reverse_heating", "clean_door"]
