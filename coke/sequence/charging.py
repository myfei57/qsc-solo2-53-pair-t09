"""装煤顺序：煤斗对位 → 集气管调压 → 桥管翻板 → 给煤。"""

from __future__ import annotations

from ..charger.machine import ChargingCar
from ..gas.collector import CollectorMain
from ..gas.flap import BridgeFlap

MAX_STEPS = 600


def charge_oven(
    charger: ChargingCar,
    collector: CollectorMain,
    flap: BridgeFlap,
    oven: str,
    hopper_target_mm: float,
    hopper_measured_mm: float,
    dt: float = 1.0,
) -> dict:
    """执行一炉装煤，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []

    alignment = charger.align_hopper(oven, hopper_target_mm, hopper_measured_mm)
    steps.append({"component": "charger", "action": "align_hopper", "detail": alignment.as_dict()})
    if not alignment.ok:
        violations.append("hopper_not_aligned")
        return {"oven": oven, "ok": False, "steps": steps, "violations": violations}

    flap.reset_latch()
    for _ in range(MAX_STEPS):
        if collector.settled():
            break
        collector.regulate(dt)
    steps.append(
        {
            "component": "gas",
            "action": "regulate_pressure",
            "detail": {
                "pressure_pa": round(collector.pressure_pa, 2),
                "target_pa": collector.limits.pressure_target_pa,
                "settled": collector.settled(),
            },
        }
    )
    if not collector.settled():
        violations.append("pressure_not_settled")
        return {"oven": oven, "ok": False, "steps": steps, "violations": violations}

    angle = flap.open()
    steps.append({"component": "gas", "action": "open_flap", "detail": {"angle_deg": angle}})

    fed_t = 0.0
    for _ in range(MAX_STEPS):
        if charger.feed_complete():
            break
        fed_t += charger.feed(dt)
    steps.append(
        {
            "component": "charger",
            "action": "feed",
            "detail": {"fed_t": round(fed_t, 3), "aligned": charger.is_aligned()},
        }
    )
    if not charger.feed_complete():
        violations.append("feed_incomplete")
        return {"oven": oven, "ok": False, "steps": steps, "violations": violations}

    flap.close()
    steps.append({"component": "gas", "action": "close_flap", "detail": {"angle_deg": flap.angle_deg}})
    return {"oven": oven, "ok": True, "steps": steps, "violations": violations, "fed_t": fed_t}
