"""推焦顺序：导焦栅对位 → 锁定导焦栅 → 推焦 → 退杆。"""

from __future__ import annotations

from ..guide.machine import GuideCar
from ..pusher.machine import PusherMachine

MAX_STEPS = 2400


def push_oven(
    pusher: PusherMachine,
    guide: GuideCar,
    oven: str,
    guide_target_mm: float,
    guide_measured_mm: float,
    stroke_target_mm: float,
    speed_mm_s: float,
    dt: float = 1.0,
) -> dict:
    """执行一炉推焦，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []

    guide.reset()
    alignment = guide.align(oven, guide_target_mm, guide_measured_mm)
    steps.append(
        {
            "component": "guide",
            "action": "align_apron",
            "detail": {**alignment.as_dict(), "tolerance_mm": guide.align_tolerance()},
        }
    )
    if not alignment.ok:
        violations.append("guide_not_aligned")
        return {"oven": oven, "ok": False, "steps": steps, "violations": violations}

    angle = guide.lock_apron()
    steps.append(
        {
            "component": "guide",
            "action": "lock_apron",
            "detail": {"apron_deg": angle, "locked": guide.is_locked()},
        }
    )

    pusher.set_speed(speed_mm_s)
    pusher.drive_to(stroke_target_mm)
    for _ in range(MAX_STEPS):
        if pusher.at_target():
            break
        pusher.advance(dt)
    steps.append(
        {
            "component": "pusher",
            "action": "extend",
            "detail": {"ram_mm": round(pusher.ram_mm, 2), "target_mm": stroke_target_mm},
        }
    )
    if not pusher.at_target():
        violations.append("stroke_incomplete")
        return {"oven": oven, "ok": False, "steps": steps, "violations": violations}

    pusher.retract()
    for _ in range(MAX_STEPS):
        if pusher.at_target():
            break
        pusher.advance(dt)
    steps.append({"component": "pusher", "action": "retract", "detail": {"ram_mm": round(pusher.ram_mm, 2)}})

    guide.unlock_apron()
    steps.append(
        {
            "component": "guide",
            "action": "unlock_apron",
            "detail": {"apron_deg": guide.snapshot().apron_deg, "locked": guide.is_locked()},
        }
    )
    return {"oven": oven, "ok": True, "steps": steps, "violations": violations}
