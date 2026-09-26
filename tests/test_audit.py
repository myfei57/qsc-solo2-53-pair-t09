"""审计留存与死代码门禁。"""

from __future__ import annotations

import os
import subprocess
import sys

from coke.errors import AlignmentError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_operations_are_captured_in_audit(platform):
    platform.start()
    platform.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=0.0)
    entries = platform.audit.entries(limit=10)
    assert entries
    assert any(item["action"] == "charge_complete" for item in entries)
    assert platform.audit.tail(3)[0]["ts"] <= platform.audit.tail(3)[-1]["ts"]
    assert platform.audit.summary()["journal_count"] > 0
    assert platform.audit.replay_segment(0)


def test_interlock_rejection_is_recorded_as_alarm(platform):
    platform.start()
    rejected = platform.push(oven="oven01", guide_target_mm=0.0, guide_measured_mm=80.0)
    assert rejected["ok"] is False
    assert "guide_not_aligned" in rejected["violations"]
    alarms = platform.audit.alarms()
    assert any(item["action"] == "interlock_rejected" for item in alarms)


def test_platform_error_is_recorded_with_component(platform):
    try:
        platform.guide.lock_apron()
    except AlignmentError as error:
        record = platform.note_error(error)
    assert record["component"] == "guide"
    assert record["action"] == "error"
    assert record["severity"] == "warning"


def test_events_are_published_to_subscribers(platform):
    seen: list[str] = []
    unsubscribe = platform.bus.subscribe("pusher", lambda event: seen.append(event.action))
    platform.push(oven="oven01", guide_target_mm=0.0, guide_measured_mm=0.0, stroke_target_mm=3200.0)
    assert "extend" in seen and "retract" in seen
    unsubscribe()
    assert platform.bus.history("pusher")


def test_deadcode_gate_reports_no_unused_symbols():
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "deadcode.py"), os.path.join(ROOT, "coke")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"unused_symbols": []' in result.stdout
    assert '"unreachable_modules": []' in result.stdout
