"""集气管装煤需求调度：优先级、排队、幂等、回退与审计一致性。"""

from __future__ import annotations

import threading

import pytest

from coke.clock import ManualClock
from coke.config import default_config
from coke.console.api import Api
from coke.errors import CokeError
from coke.eventbus import EventBus
from coke.gas.collector import CollectorMain
from coke.gas.demand import URGENT_BONUS, DemandScheduler, OvenCondition

INITIAL_PA = 30.0


def _scheduler(max_steps: int = 600, with_bus: bool = True):
    collector = CollectorMain(default_config().collector, initial_pa=INITIAL_PA)
    bus = EventBus() if with_bus else None
    events: list = []
    if bus is not None:
        bus.subscribe("*", events.append)
    scheduler = DemandScheduler(collector, ManualClock(), bus, max_steps=max_steps)
    return scheduler, collector, events


def test_priority_is_dynamic_by_condition_not_oven_number():
    assert OvenCondition("oven09", expected_disturbance_pa=40.0).priority() == 40
    # 同一个炉况，炉号不同优先级相同：优先级按炉况动态算，不按炉号固定。
    assert OvenCondition("oven01", expected_disturbance_pa=40.0).priority() == 40
    assert OvenCondition("oven02", 10.0, backflow_risk=True).priority() == 10 + URGENT_BONUS
    assert OvenCondition("oven03").priority() == 0


def test_normal_requests_are_first_come_first_served():
    scheduler, _, _ = _scheduler()
    scheduler.request("a", OvenCondition("oven01", expected_disturbance_pa=50.0))
    scheduler.request("b", OvenCondition("oven02", expected_disturbance_pa=5.0))
    scheduler.request("c", OvenCondition("oven03", expected_disturbance_pa=30.0))
    order = [item["key"] for item in scheduler.snapshot()["queued"]]
    # 常规档严格先到先得，预计扰动量不改变常规档的先后。
    assert order == ["a", "b", "c"]


def test_urgent_condition_preempts_queued_normals():
    scheduler, _, _ = _scheduler()
    scheduler.request("a", OvenCondition("oven01"))
    scheduler.request("b", OvenCondition("oven02"))
    scheduler.request("u1", OvenCondition("oven03", backflow_risk=True))
    scheduler.request("u2", OvenCondition("oven04", 60.0, backflow_risk=True))
    queued = scheduler.snapshot()["queued"]
    # 紧急档插队到全部常规需求之前，紧急档内部按优先级再按到达先后。
    assert [item["key"] for item in queued] == ["u2", "u1", "a", "b"]
    assert queued[0]["position"] == 1


def test_running_pre_adjust_is_not_interrupted():
    scheduler, collector, _ = _scheduler()
    scheduler.request("a", OvenCondition("oven01"))
    first = scheduler.pre_adjust("a")
    assert first.status == "applied"
    assert collector.settled()
    # 已授权执行的预调不被打断：紧急请求只能插排队，不能抢执行位。
    scheduler.request("u", OvenCondition("oven02", backflow_risk=True))
    assert scheduler.pre_adjust("u").status == "queued"
    scheduler.release("a")
    assert scheduler.pre_adjust("u").status == "applied"


def test_concurrent_triggers_apply_only_once():
    scheduler, _, events = _scheduler()
    scheduler.request("k", OvenCondition("oven01"))
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(scheduler.pre_adjust("k")))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert {ticket.status for ticket in results} == {"applied"}
    assert {ticket.before_pa for ticket in results} == {INITIAL_PA}
    applied = [event for event in events if event.action == "pre_adjust_applied"]
    granted = [event for event in events if event.action == "demand_granted"]
    assert len(applied) == 1
    assert len(granted) == 1


def test_duplicate_request_returns_same_ticket_without_new_event():
    scheduler, _, events = _scheduler()
    first = scheduler.request("k", OvenCondition("oven01"))
    again = scheduler.request("k", OvenCondition("oven01", backflow_risk=True))
    assert again == first
    assert [event for event in events if event.action == "demand_queued"].__len__() == 1


def test_repeat_trigger_keeps_pressure_and_rollback_baseline():
    scheduler, collector, _ = _scheduler()
    scheduler.request("k", OvenCondition("oven01"))
    applied = scheduler.pre_adjust("k")
    collector.disturb(-20.0)
    repeated = scheduler.pre_adjust("k")
    # 重复触发不重新调压，也不覆盖调压前记下的回退基准。
    assert repeated.before_pa == INITIAL_PA
    assert collector.pressure_pa == applied.after_pa - 20.0
    scheduler.rollback("k")
    assert collector.pressure_pa == INITIAL_PA


def test_failed_pre_adjust_rolls_back_to_previous_pressure():
    scheduler, collector, events = _scheduler(max_steps=3)
    scheduler.request("k", OvenCondition("oven01"))
    ticket = scheduler.pre_adjust("k", dt=1.0)
    assert ticket.status == "rolled_back"
    assert collector.pressure_pa == INITIAL_PA
    rolled = [event for event in events if event.action == "pre_adjust_rolled_back"]
    assert len(rolled) == 1
    assert rolled[0].payload["severity"] == "warning"
    assert rolled[0].payload["reason"] == "not_settled"


def test_manual_rollback_restores_and_is_idempotent():
    scheduler, collector, events = _scheduler()
    scheduler.request("k", OvenCondition("oven01"))
    applied = scheduler.pre_adjust("k")
    assert collector.settled()
    rolled = scheduler.rollback("k")
    assert rolled.status == "rolled_back"
    assert collector.pressure_pa == applied.before_pa
    again = scheduler.rollback("k")
    assert again.status == "rolled_back"
    assert [event for event in events if event.action == "pre_adjust_rolled_back"].__len__() == 1


def test_scheduler_works_without_event_bus():
    scheduler, collector, _ = _scheduler(with_bus=False)
    scheduler.request("k", OvenCondition("oven01"))
    assert scheduler.pre_adjust("k").status == "applied"
    assert collector.settled()
    assert scheduler.rollback("k").status == "rolled_back"
    assert collector.pressure_pa == INITIAL_PA


def test_unknown_key_is_rejected():
    scheduler, _, _ = _scheduler()
    with pytest.raises(CokeError):
        scheduler.rollback("ghost")
    with pytest.raises(CokeError):
        scheduler.release("ghost")


def test_charge_pre_adjusts_then_releases(platform):
    platform.start()
    report = platform.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=0.0)
    assert report["ok"] is True
    assert report["schedule"]["status"] == "released"
    snapshot = platform.gas_schedule_snapshot()
    assert snapshot["counts"]["terminal"] == 1
    actions = [entry["action"] for entry in platform.audit.tail(100)]
    for expected in ("demand_queued", "demand_granted", "pre_adjust_applied", "demand_released"):
        assert expected in actions
    # 调度顺序有时序：授权在预调前，预调在释放前。
    assert actions.index("demand_granted") < actions.index("pre_adjust_applied")
    assert actions.index("pre_adjust_applied") < actions.index("demand_released")


def test_charge_partial_failure_rolls_back_pressure(platform):
    platform.start()
    before = platform.collector.pressure_pa
    report = platform.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=60.0)
    assert report["ok"] is False
    assert "hopper_not_aligned" in report["violations"]
    assert platform.collector.pressure_pa == before
    rolled = [
        entry
        for entry in platform.audit.tail(100)
        if entry["action"] == "pre_adjust_rolled_back"
    ]
    assert rolled and rolled[-1]["payload"]["reason"] == "charge_incomplete"


def test_charge_queues_while_slot_held_and_retries_with_same_key(platform):
    platform.start()
    first = platform.schedule_pre_adjust(oven="oven01", key="k1")
    assert first["ticket"]["status"] == "applied"
    queued = platform.charge(oven="oven02", schedule_key="req-oven02")
    assert queued["queued"] is True
    assert queued["steps"] == []
    assert queued["schedule"]["position"] == 1
    platform.release_pre_adjust("k1")
    done = platform.charge(oven="oven02", schedule_key="req-oven02")
    assert done["ok"] is True
    assert done["schedule"]["created"] is False
    assert done["schedule"]["status"] == "released"


def test_schedule_events_persist_to_journal_in_order(platform):
    platform.start()
    platform.schedule_pre_adjust(oven="oven01", key="k1", expected_disturbance_pa=25.0)
    persisted = [
        record
        for record in platform.audit.replay_from_journal()
        if record.get("payload", {}).get("key") == "k1"
    ]
    assert [record["action"] for record in persisted] == [
        "demand_queued",
        "demand_granted",
        "pre_adjust_applied",
    ]
    seqs = [record["payload"]["seq"] for record in persisted]
    assert seqs == sorted(seqs)
    applied = persisted[-1]["payload"]
    # 压力、调度记录与审计同口径：审计里的前后压力就是票据里的值。
    assert applied["before_pa"] == INITIAL_PA
    ticket = platform.gas_schedule.ticket_for("k1")
    assert applied["after_pa"] == round(ticket.after_pa, 2)


def test_status_exposes_schedule_policy(platform):
    schedule = platform.status()["gas_schedule"]
    assert schedule["policy"]["priority"] == "dynamic_by_condition"
    assert schedule["policy"]["conflict"] == "urgent_preempts_normal_fcfs"
    assert schedule["counts"]["issued"] == 0


def test_console_endpoints_display_and_drive_schedule(platform):
    api = Api(platform)
    platform.start()
    status, payload = api.handle(
        "POST",
        "/api/schedule/pre_adjust",
        {},
        {"oven": "oven01", "key": "k1", "expected_disturbance_pa": 25},
    )
    assert status == 200
    assert payload["created"] is True
    assert payload["ticket"]["status"] == "applied"
    _, again = api.handle("POST", "/api/schedule/pre_adjust", {}, {"oven": "oven01", "key": "k1"})
    assert again["created"] is False
    assert again["ticket"]["status"] == "applied"
    status, snapshot = api.handle("GET", "/api/schedule", {}, {})
    assert status == 200
    assert snapshot["policy"]["priority"] == "dynamic_by_condition"
    assert snapshot["active"]["key"] == "k1"
    _, rolled = api.handle("POST", "/api/schedule/rollback", {}, {"key": "k1"})
    assert rolled["ticket"]["status"] == "rolled_back"
    assert rolled["pressure_pa"] == INITIAL_PA
    error_status, _ = api.handle("POST", "/api/schedule/rollback", {}, {"key": "ghost"})
    assert error_status == 409
    missing_status, _ = api.handle("POST", "/api/schedule/release", {}, {})
    assert missing_status == 409
