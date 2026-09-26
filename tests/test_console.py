"""控制台接口与 HTTP 服务。"""

from __future__ import annotations

from coke.console.api import Api
from coke.console.server import ConsoleServer, probe_endpoints


def test_api_returns_status_and_routes(platform):
    api = Api(platform)
    status, payload = api.handle("GET", "/api/status", {}, {})
    assert status == 200
    assert payload["platform"] == platform.config.name
    routes = api.routes()
    assert any(route["path"] == "/api/push" for route in routes)


def test_api_unknown_path_is_404(platform):
    api = Api(platform)
    status, payload = api.handle("GET", "/api/does-not-exist", {}, {})
    assert status == 404
    assert payload["error"] == "not_found"


def test_api_interlock_error_is_409(platform):
    api = Api(platform)
    status, payload = api.handle(
        "POST", "/api/push", {}, {"guide_target_mm": 0.0, "guide_measured_mm": 90.0}
    )
    assert status == 200
    assert payload["ok"] is False
    status_error, error_payload = api.handle("POST", "/api/calibrate", {}, {"value_mm": -1})
    assert status_error == 409
    assert error_payload["component"] == "pusher"


def test_api_timeline_and_journal(platform):
    api = Api(platform)
    platform.start()
    platform.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=0.0)
    status, timeline = api.handle("GET", "/api/timeline", {"oven": "oven01"}, {})
    assert status == 200
    assert timeline["timeline"][0]["step"] == 1
    status, journal = api.handle("GET", "/api/journal", {}, {})
    assert status == 200
    assert journal["count"] > 0


def test_readiness_and_step_endpoints(platform):
    api = Api(platform)
    platform.start()
    platform.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=0.0)
    platform.cycle(dt=1.0)
    status, ready = api.handle("GET", "/api/readiness", {}, {})
    assert status == 200
    assert ready["ready"] is True
    status, cycle = api.handle("POST", "/api/step", {}, {"dt": 1.0})
    assert status == 200
    assert cycle["cycle"] == 2
    status, events = api.handle("GET", "/api/events", {"topic": "charger"}, {})
    assert status == 200
    assert events["events"]
    status, trend = api.handle("GET", "/api/trend", {"signal": "collector_pressure"}, {})
    assert status == 200
    assert trend["samples"]
    status, store = api.handle("GET", "/api/store", {}, {})
    assert status == 200
    assert "platform_state" in store["documents"]


def test_api_rejects_bad_parameter(platform):
    api = Api(platform)
    status, payload = api.handle("POST", "/api/step", {}, {"dt": "not-a-number"})
    assert status == 409
    assert payload["component"] == "console"


def test_server_serves_real_http(platform):
    platform.start()
    server = ConsoleServer(platform, host="127.0.0.1", port=0)
    base_url = server.start()
    try:
        probe = probe_endpoints(base_url, ["/api/status", "/api/readiness", "/api/topology", "/api/nope"])
    finally:
        server.stop()
    assert probe["/api/status"]["ok"] is True
    assert probe["/api/readiness"]["ok"] is True
    assert probe["/api/topology"]["ok"] is True
    assert probe["/api/nope"]["ok"] is False
    assert server.port == 0
