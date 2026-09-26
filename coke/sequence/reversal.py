"""加热换向顺序：废气阀 → 煤气阀 → 炉温确认（两相间互斥切换）。"""

from __future__ import annotations

from ..heating.machine import HeatingReversal
from ..heating.temperature import OvenTemperature
from ..heating.valvetrain import ValveTrain


def reverse_heating(
    reversal: HeatingReversal,
    valves: ValveTrain,
    temperature: OvenTemperature,
    oven: str,
    next_temperature_c: float,
) -> dict:
    """执行一次换向，返回带步骤与违约项的报告。"""

    steps: list[dict] = []
    violations: list[str] = []

    if not reversal.due():
        violations.append("reversal_not_due")
        return {"oven": oven, "ok": False, "steps": steps, "violations": violations}

    if valves.waste_open:
        valves.close_waste_gas()
        steps.append({"component": "heating", "action": "close_waste_gas", "detail": {"open": valves.waste_open}})
        valves.open_gas()
        steps.append({"component": "heating", "action": "open_gas", "detail": {"open": valves.gas_open}})
        direction = "waste_to_gas"
    else:
        valves.close_gas()
        steps.append({"component": "heating", "action": "close_gas", "detail": {"open": valves.gas_open}})
        valves.open_waste_gas()
        steps.append({"component": "heating", "action": "open_waste_gas", "detail": {"open": valves.waste_open}})
        direction = "gas_to_waste"

    temperature.update(next_temperature_c)
    confirmed = temperature.confirmed()
    steps.append(
        {
            "component": "heating",
            "action": "confirm_temperature",
            "detail": {"temperature_c": round(temperature.value_c, 2), "confirmed": confirmed},
        }
    )
    if confirmed:
        reversal.mark_reversed()
    else:
        violations.append("temp_not_confirmed")
    return {"oven": oven, "ok": confirmed, "steps": steps, "violations": violations, "direction": direction}
