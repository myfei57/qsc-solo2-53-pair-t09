"""平台装配、控制循环与并发仲裁。"""

from __future__ import annotations

from coke.app import build_platform
from coke.config import default_config


def test_cycle_regulates_collector_pressure(platform):
    platform.start()
    target = platform.collector.limits.pressure_target_pa
    for _ in range(40):
        platform.cycle(dt=1.0)
    assert platform.collector.settled()
    assert abs(platform.collector.pressure_pa - target) <= platform.collector.limits.pressure_band_pa


def test_disturbance_pulls_pressure_and_recovers(platform):
    platform.start()
    disturbed = platform.disturb_collector(delta_pa=-60.0)
    assert disturbed["settled"] is False
    for _ in range(30):
        platform.cycle(dt=1.0)
    assert platform.collector.settled()


def test_concurrency_probe_converges_to_single_speed(platform):
    platform.start()
    outcome = platform.concurrency_probe(rounds=12)
    assert outcome["winner"] == "manual_console"
    assert outcome["committed_mm_s"] == platform.config.pusher.speed_min_mm_s
    assert outcome["committed_on_machine"] == outcome["committed_mm_s"]
    assert set(outcome["writers"]) == {"auto_cycle", "manual_console"}


def test_calibrate_stroke_updates_baseline(platform):
    platform.start()
    result = platform.calibrate_stroke(3212.0)
    assert result["after_mm"] == 3212.0
    assert result["epoch"] == 1
    assert platform.status()["stroke"]["baseline_mm"] == 3212.0


def test_status_and_snapshot_expose_components(platform):
    platform.start()
    platform.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=0.0)
    status = platform.status()
    for key in ("pusher", "guide", "charger", "quench", "gas", "door", "heating", "dust", "audit"):
        assert key in status
    snapshot = platform.snapshot()
    assert snapshot["topology"]["order"][0] == "charge"
    assert snapshot["namespaces"]["count"] >= 8


def test_operations_and_cycles_persist_across_restart(tmp_path, clock):
    storage = str(tmp_path / "state")
    first = build_platform(default_config(), clock=clock, storage_root=storage)
    first.start()
    first.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=0.0)
    first.cycle(dt=1.0)
    assert first.status()["operations"] == 1

    second = build_platform(default_config(), clock=clock, storage_root=storage)
    status = second.status()
    assert status["operations"] >= 1
    assert status["cycles"] >= 1


def test_heating_state_restores_from_journal(tmp_path, clock):
    storage = str(tmp_path / "state")
    config = default_config()
    first = build_platform(config, clock=clock, storage_root=storage)
    first.start()
    clock.advance(config.heating.reversal_interval_s)
    assert first.reverse(oven="oven01")["ok"] is True

    second = build_platform(config, clock=clock, storage_root=storage)
    assert second.reversal.count() >= 1


def test_reset_state_clears_document(platform):
    platform.start()
    platform.cycle(dt=1.0)
    assert platform.reset_state() is True
    assert platform.reset_state() is False
