"""炉门清扫顺序：松开闩锁 → 开炉门 → 清扫 → 复位闩锁。"""

from __future__ import annotations

from ..door.machine import DoorCleaner

MAX_STEPS = 600


def clean_door(door: DoorCleaner, oven: str, dt: float = 1.0) -> dict:
    """执行一炉炉门清扫，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []

    door.latch.release()
    steps.append(
        {
            "component": "door",
            "action": "release_latch",
            "detail": {"engaged": door.latch.is_engaged(), "position_mm": door.latch.position_mm},
        }
    )

    door.open_door(oven)
    steps.append({"component": "door", "action": "open_door", "detail": {"oven": oven}})

    for _ in range(MAX_STEPS):
        if door.progress() >= 1.0:
            break
        door.clean(dt)
    steps.append({"component": "door", "action": "clean", "detail": {"progress": round(door.progress(), 3)}})
    if door.progress() < 1.0:
        violations.append("clean_incomplete")
        return {"oven": oven, "ok": False, "steps": steps, "violations": violations}

    cycles = door.mark_cleaned()
    steps.append({"component": "door", "action": "mark_cleaned", "detail": {"cycles": cycles}})

    door.close_door()
    steps.append(
        {
            "component": "door",
            "action": "close_door",
            "detail": {"latch_engaged": door.latch.is_engaged(), "cleaned": door.is_cleaned()},
        }
    )
    return {"oven": oven, "ok": True, "steps": steps, "violations": violations}
