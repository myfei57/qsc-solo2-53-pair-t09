"""加热换向与炉门清扫顺序。"""

from __future__ import annotations

import pytest

from coke.clock import ManualClock
from coke.config import default_config
from coke.door.latch import DoorLatch
from coke.door.machine import DoorCleaner
from coke.errors import InterlockError
from coke.heating.machine import HeatingReversal
from coke.heating.temperature import OvenTemperature
from coke.heating.valvetrain import ValveTrain
from coke.sequence import clean_door, reverse_heating


def test_valve_train_enforces_mutual_exclusion():
    valves = ValveTrain()
    assert valves.waste_open is True
    with pytest.raises(InterlockError):
        valves.open_gas()
    valves.close_waste_gas()
    valves.open_gas()
    assert valves.gas_open is True
    with pytest.raises(InterlockError):
        valves.open_waste_gas()
    with pytest.raises(InterlockError):
        valves.open_gas()
    valves.close_gas()
    valves.open_waste_gas()
    assert valves.reversals() == 1


def test_reversal_requires_due_interval():
    clock = ManualClock()
    config = default_config()
    reversal = HeatingReversal(config.heating, clock)
    valves = ValveTrain()
    temperature = OvenTemperature(config.heating)
    early = reverse_heating(reversal, valves, temperature, "oven01", config.heating.temp_target_c)
    assert early["ok"] is False
    assert "reversal_not_due" in early["violations"]

    clock.advance(config.heating.reversal_interval_s)
    on_time = reverse_heating(reversal, valves, temperature, "oven01", config.heating.temp_target_c)
    assert on_time["ok"] is True
    assert on_time["direction"] == "waste_to_gas"
    assert reversal.count() == 1
    order = [step["action"] for step in on_time["steps"]]
    assert order.index("close_waste_gas") < order.index("open_gas")
    assert order.index("open_gas") < order.index("confirm_temperature")


def test_reversal_marks_unconfirmed_temperature():
    clock = ManualClock()
    config = default_config()
    reversal = HeatingReversal(config.heating, clock)
    valves = ValveTrain()
    temperature = OvenTemperature(config.heating)
    clock.advance(config.heating.reversal_interval_s)
    report = reverse_heating(reversal, valves, temperature, "oven01", config.heating.temp_target_c + 400.0)
    assert report["ok"] is False
    assert "temp_not_confirmed" in report["violations"]
    assert reversal.count() == 0
    assert temperature.offset_c() == pytest.approx(400.0)


def test_door_latch_release_requires_full_travel():
    latch = DoorLatch(60.0)
    with pytest.raises(InterlockError):
        latch.release(position_mm=20.0)
    assert latch.release() is False
    assert latch.position_mm == 0.0


def test_door_clean_requires_loosened_latch():
    config = default_config()
    door = DoorCleaner(config.door, DoorLatch(config.door.latch_travel_mm))
    door.open_door("oven01")
    with pytest.raises(InterlockError):
        door.clean(1.0)
    report = clean_door(door, "oven01")
    assert report["ok"] is True
    order = [step["action"] for step in report["steps"]]
    assert order.index("release_latch") < order.index("open_door")
    assert order.index("open_door") < order.index("clean")
    assert order.index("clean") < order.index("close_door")
    assert door.latch.is_engaged() is True
    assert door.latch.cycles() == 1


def test_mark_cleaned_requires_completion():
    config = default_config()
    door = DoorCleaner(config.door, DoorLatch(config.door.latch_travel_mm))
    door.open_door("oven01")
    door.latch.release()
    door.clean(5.0)
    with pytest.raises(InterlockError):
        door.mark_cleaned()
