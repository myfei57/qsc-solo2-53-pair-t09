"""跨组件操作顺序与联锁。"""

from __future__ import annotations

import pytest

from coke.charger.machine import ChargingCar
from coke.config import default_config
from coke.errors import InterlockError
from coke.gas.collector import CollectorMain
from coke.gas.flap import BridgeFlap
from coke.gas.latch import FlapLatch
from coke.guide.machine import GuideCar
from coke.pusher.machine import PusherMachine
from coke.pusher.stroke import StrokeBaseline
from coke.quench.machine import QuenchCar
from coke.sequence import charge_oven, push_oven, quench_oven


def test_charge_requires_hopper_alignment():
    config = default_config()
    charger = ChargingCar(config.charger)
    collector = CollectorMain(config.collector)
    flap = BridgeFlap(FlapLatch())
    report = charge_oven(charger, collector, flap, "oven01", 0.0, 60.0)
    assert report["ok"] is False
    assert "hopper_not_aligned" in report["violations"]
    assert [step["action"] for step in report["steps"]] == ["align_hopper"]


def test_charge_pressure_precedes_flap_and_feed():
    config = default_config()
    charger = ChargingCar(config.charger)
    collector = CollectorMain(config.collector)
    flap = BridgeFlap(FlapLatch())
    report = charge_oven(charger, collector, flap, "oven01", 0.0, 0.0)
    assert report["ok"] is True
    order = [step["action"] for step in report["steps"]]
    assert order.index("align_hopper") < order.index("regulate_pressure")
    assert order.index("regulate_pressure") < order.index("open_flap")
    assert order.index("open_flap") < order.index("feed")
    assert charger.feed_complete()
    assert flap.latch.is_engaged()
    assert flap.latch.cycles() == 1


def test_flap_rejects_double_open_until_reset():
    flap = BridgeFlap(FlapLatch())
    flap.open()
    with pytest.raises(InterlockError):
        flap.open()
    assert flap.reset_latch() is False
    flap.open()
    assert flap.latch.cycles() == 2


def test_push_requires_guide_alignment_and_locks_apron():
    config = default_config()
    pusher = PusherMachine(config.pusher)
    guide = GuideCar(config.guide)
    rejected = push_oven(pusher, guide, "oven01", 0.0, 90.0, 3200.0, 24.0)
    assert rejected["ok"] is False
    assert "guide_not_aligned" in rejected["violations"]
    assert guide.is_locked() is False

    accepted = push_oven(pusher, guide, "oven01", 0.0, 0.0, 3200.0, 24.0)
    assert accepted["ok"] is True
    order = [step["action"] for step in accepted["steps"]]
    assert order.index("align_apron") < order.index("lock_apron")
    assert order.index("lock_apron") < order.index("extend")
    assert order.index("extend") < order.index("retract")
    assert order.index("retract") < order.index("unlock_apron")
    assert pusher.snapshot().strokes == 1
    assert guide.is_locked() is False


def test_push_beyond_max_stroke_is_rejected():
    config = default_config()
    pusher = PusherMachine(config.pusher)
    with pytest.raises(InterlockError):
        pusher.drive_to(config.pusher.max_stroke_mm + 1.0)


def test_quench_spray_requires_travel():
    config = default_config()
    quench = QuenchCar(config.quench)
    quench.receive("oven01")
    with pytest.raises(InterlockError):
        quench.start_spray()
    report = quench_oven(quench, "oven01")
    assert report["ok"] is True
    order = [step["action"] for step in report["steps"]]
    assert order.index("receive") < order.index("travel")
    assert order.index("travel") < order.index("start_spray")
    assert order.index("start_spray") < order.index("spray")
    assert quench.spray.complete()
    assert quench.snapshot().water_m3 > 0


def test_stroke_baseline_reports_deviation():
    baseline = StrokeBaseline(3200.0, 25.0)
    near = baseline.check(3210.0)
    far = baseline.check(3300.0)
    assert near["ok"] is True
    assert far["ok"] is False
    baseline.calibrate(3212.0)
    assert baseline.epoch == 1
    assert baseline.check(3212.0)["ok"] is True
