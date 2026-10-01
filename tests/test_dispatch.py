"""装煤需求调度：优先级、仲裁、幂等、回退与一致性。"""

from __future__ import annotations

import dataclasses
import threading

import pytest

from coke.app import build_platform
from coke.config import DispatchLimits, default_config
from coke.console.api import Api
from coke.dispatch.priority import STAGE_WEIGHT, priority_of
from coke.errors import CokeError, InterlockError


def test_priority_is_dynamic_by_condition_and_recomputable():
    # 定死：按炉况动态算，不按炉号固定；同一炉不同阶段优先级不同。
    assert priority_of("early", 0.0, 30.0, 200) == STAGE_WEIGHT["early"]
    assert priority_of("early", 0.0, 30.0, 200) > priority_of("mid", 0.0, 30.0, 200)
    assert priority_of("mid", 0.0, 30.0, 200) > priority_of("late", 0.0, 30.0, 200)
    # 等待老化：每满一个步长加 1 分，封顶。
    assert priority_of("mid", 90.0, 30.0, 200) == STAGE_WEIGHT["mid"] + 3
    assert priority_of("mid", 100_000.0, 30.0, 200) == STAGE_WEIGHT["mid"] + 200
    with pytest.raises(ValueError):
        priority_of("bogus", 0.0, 30.0, 200)


def test_submit_is_idempotent_per_oven(platform):
    platform.start()
    first = platform.submit_charge_demand(oven="oven01", coking_stage="mid")
    second = platform.submit_charge_demand(oven="oven01", coking_stage="early")
    assert second["demand_id"] == first["demand_id"]
    assert second["idempotent_replay"] is True
    submitted = [r for r in platform.dispatch_snapshot()["recent"] if r["event"] == "submitted"]
    assert len(submitted) == 1
    with pytest.raises(CokeError):
        platform.submit_charge_demand(oven="oven02", coking_stage="bogus")


def test_fcfs_when_pressure_in_band_and_no_early_stage(platform):
    platform.start()
    platform.disturb_collector(50.0)  # 30 → 80 Pa，进入目标带 [72, 108]
    assert platform.collector.settled()
    ids = [
        platform.submit_charge_demand(oven=f"oven0{i}", coking_stage="mid")["demand_id"]
        for i in (1, 2, 3)
    ]
    order = []
    for _ in range(3):
        decision = platform.dispatch_next()
        assert decision["mode"] == "fcfs"
        assert decision["mode_reason"] == "calm"
        order.append(decision["demand_id"])
        platform.complete_charge_demand(decision["demand_id"])
    assert order == ids


def test_preempt_when_early_stage_present(platform):
    platform.start()
    platform.disturb_collector(50.0)  # 压力在带内，仅炉况触发插队
    platform.submit_charge_demand(oven="oven01", coking_stage="mid")
    platform.submit_charge_demand(oven="oven02", coking_stage="early")
    decision = platform.dispatch_next()
    assert decision["mode"] == "preempt"
    assert decision["mode_reason"] == "early_stage_present"
    assert decision["oven"] == "oven02"
    platform.complete_charge_demand(decision["demand_id"])
    followup = platform.dispatch_next()
    assert followup["oven"] == "oven01"


def test_preempt_when_pressure_out_of_band(platform):
    platform.start()  # 初始 30 Pa，越出目标带
    assert not platform.collector.settled()
    platform.submit_charge_demand(oven="oven01", coking_stage="late")
    platform.submit_charge_demand(oven="oven02", coking_stage="mid")
    decision = platform.dispatch_next()
    assert decision["mode"] == "preempt"
    assert decision["mode_reason"] == "pressure_out_of_band"
    assert decision["oven"] == "oven02"  # mid 权重高于 late，插队


def test_concurrent_dispatch_is_idempotent(platform):
    platform.start()
    platform.submit_charge_demand(oven="oven01", coking_stage="mid")
    results: list[dict] = []
    threads = [threading.Thread(target=lambda: results.append(platform.dispatch_next())) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    applied = [r for r in results if not r.get("idempotent_replay")]
    assert len(applied) == 1  # 预调只执行一次
    assert {r["demand_id"] for r in results} == {applied[0]["demand_id"]}
    assert platform.collector.pressure_pa == applied[0]["prereg_target_pa"]
    records = [r for r in platform.dispatch_snapshot()["recent"] if r["event"] == "prereg_applied"]
    assert len(records) == 1  # 流水不重复


def test_rollback_restores_pressure_before_prereg(platform):
    platform.start()
    before = platform.collector.pressure_pa
    platform.submit_charge_demand(oven="oven01", coking_stage="mid")
    decision = platform.dispatch_next()
    assert platform.collector.pressure_pa == decision["prereg_target_pa"]
    rolled = platform.rollback_charge_demand(decision["demand_id"])
    assert rolled["restored"] is True
    assert platform.collector.pressure_pa == before  # 回退到调压前的值
    again = platform.rollback_charge_demand(decision["demand_id"])
    assert again["idempotent_replay"] is True
    assert platform.collector.pressure_pa == before
    records = [r for r in platform.dispatch_snapshot()["recent"] if r["event"] == "rolled_back"]
    assert len(records) == 1


def test_partial_prereg_rolls_back(tmp_path, clock):
    config = dataclasses.replace(default_config(), dispatch=DispatchLimits(30.0, 200, 0.6, 1))
    platform = build_platform(config, clock=clock, storage_root=str(tmp_path / "state"))
    platform.start()
    before = platform.collector.pressure_pa
    report = platform.charge_scheduled(oven="oven01", coking_stage="mid")
    assert report["ok"] is False
    assert "prereg_partial" in report["violations"]
    assert platform.collector.pressure_pa == before  # 部分失败后回退到调压前的值


def test_charge_scheduled_full_saga_and_consistency(platform):
    platform.start()
    report = platform.charge_scheduled(
        oven="oven01", coking_stage="early", hopper_target_mm=0.0, hopper_measured_mm=0.0
    )
    assert report["ok"] is True
    assert report["dispatch"]["decision"]["state"] == "applied"
    assert "release" in report
    demand_id = report["dispatch"]["submit"]["demand_id"]

    # 调度记录、压力与审计三者一致：同一 demand_id、序号单调、压力值吻合。
    entries = platform.audit.entries(limit=100)
    dispatch_entries = [
        e for e in entries if e["component"] == "dispatch" and e["payload"].get("demand_id") == demand_id
    ]
    actions = [e["action"] for e in dispatch_entries]
    assert "submitted" in actions and "prereg_applied" in actions and "released" in actions
    seqs = sorted(e["payload"]["seq"] for e in dispatch_entries)
    recent = [r for r in platform.dispatch_snapshot()["recent"] if r["demand_id"] == demand_id]
    assert sorted(r["seq"] for r in recent) == seqs
    prereg = next(r for r in recent if r["event"] == "prereg_applied")
    assert prereg["pressure_after_pa"] == prereg["prereg_target_pa"]
    assert platform.dispatch_snapshot()["state_counts"]["released"] == 1


def test_charge_scheduled_failure_rolls_back(platform):
    platform.start()
    before = platform.collector.pressure_pa
    report = platform.charge_scheduled(
        oven="oven01", coking_stage="mid", hopper_target_mm=0.0, hopper_measured_mm=90.0
    )
    assert report["ok"] is False
    assert "hopper_not_aligned" in report["violations"]
    assert "rollback" in report
    assert platform.collector.pressure_pa == before
    assert platform.dispatch_snapshot()["state_counts"]["rolled_back"] == 1


def test_charge_scheduled_waits_when_grant_busy(platform):
    platform.start()
    platform.submit_charge_demand(oven="oven01", coking_stage="mid")
    platform.dispatch_next()  # oven01 持有授权
    report = platform.charge_scheduled(oven="oven02", coking_stage="mid")
    assert report["ok"] is False
    assert "dispatch_not_granted" in report["violations"]


def test_complete_and_rollback_guards(platform):
    platform.start()
    submit = platform.submit_charge_demand(oven="oven01", coking_stage="mid")
    with pytest.raises(InterlockError):
        platform.complete_charge_demand(submit["demand_id"])  # 未授权预调
    with pytest.raises(InterlockError):
        platform.rollback_charge_demand(submit["demand_id"])  # 无压可回
    with pytest.raises(CokeError):
        platform.complete_charge_demand("dm-unknown")
    decision = platform.dispatch_next()
    platform.rollback_charge_demand(decision["demand_id"])
    with pytest.raises(InterlockError):
        platform.complete_charge_demand(decision["demand_id"])  # 已回退禁止放行


def test_dispatch_state_survives_restart(tmp_path, clock):
    storage = str(tmp_path / "state")
    first = build_platform(default_config(), clock=clock, storage_root=storage)
    first.start()
    first.submit_charge_demand(oven="oven01", coking_stage="early")
    decision = first.dispatch_next()

    second = build_platform(default_config(), clock=clock, storage_root=storage)
    snap = second.dispatch_snapshot()
    assert snap["active"]["demand_id"] == decision["demand_id"]
    assert snap["active"]["state"] == "applied"
    assert snap["records_total"] >= 2


def test_console_dispatch_endpoints(platform):
    api = Api(platform)
    platform.start()
    status, submit = api.handle("POST", "/api/dispatch/submit", {}, {"oven": "oven01", "coking_stage": "early"})
    assert status == 200
    assert submit["event"] == "submitted"
    status, decision = api.handle("POST", "/api/dispatch/run", {}, {})
    assert status == 200
    assert decision["state"] == "applied"
    status, snap = api.handle("GET", "/api/dispatch", {}, {})
    assert status == 200
    assert snap["active"]["oven"] == "oven01"
    status, release = api.handle("POST", "/api/dispatch/complete", {}, {"demand_id": submit["demand_id"]})
    assert status == 200
    assert release["event"] == "released"
    status, snap = api.handle("GET", "/api/dispatch", {}, {})
    assert snap["active"] is None
    status, error = api.handle("POST", "/api/dispatch/submit", {}, {"oven": "oven02", "coking_stage": "bogus"})
    assert status == 409
    assert error["component"] == "dispatch"


def test_charge_scheduled_via_console(platform):
    api = Api(platform)
    platform.start()
    status, report = api.handle(
        "POST",
        "/api/charge-scheduled",
        {},
        {"oven": "oven03", "coking_stage": "mid", "hopper_target_mm": 0.0, "hopper_measured_mm": 0.0},
    )
    assert status == 200
    assert report["ok"] is True
    assert "dispatch" in platform.status()
