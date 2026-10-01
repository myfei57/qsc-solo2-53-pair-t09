"""控制台接口处理器。

每个接口都是对平台公开方法的一次调用；动作类接口把请求体里的参数透传给平台，
缺少必填字段时返回 ``400``，平台异常统一转成 ``409`` 并在响应里带上组件名。
"""

from __future__ import annotations

from ..app import Platform
from ..audit.timeline import build_timeline
from ..errors import CokeError
from .router import Router


def _as_float(body: dict, key: str, default: float) -> float:
    value = body.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise CokeError(f"参数 {key!r} 必须是数值", component="console") from error


class Api:
    """把 HTTP 请求翻译成平台调用。"""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform
        self._router = Router()
        self._register()

    @property
    def platform(self) -> Platform:
        return self._platform

    def _register(self) -> None:
        add = self._router.add
        add("GET", "/api/status", lambda params, body: self._platform.status())
        add("GET", "/api/snapshot", lambda params, body: self._platform.snapshot())
        add("GET", "/api/topology", lambda params, body: self._platform.topology_summary())
        add("GET", "/api/namespaces", lambda params, body: self._platform.namespaces_describe())
        add("GET", "/api/audit", self._audit)
        add("GET", "/api/alarms", lambda params, body: {"alarms": self._platform.audit.alarms()})
        add("GET", "/api/events", self._events)
        add("GET", "/api/trend", self._trend)
        add("GET", "/api/store", self._store)
        add("GET", "/api/timeline", self._timeline)
        add("GET", "/api/journal", self._journal)
        add("GET", "/api/readiness", self._readiness)
        add("GET", "/api/schedule", lambda params, body: self._platform.gas_schedule_snapshot())
        add("POST", "/api/step", self._step)
        add("POST", "/api/charge", self._charge)
        add("POST", "/api/schedule/pre_adjust", self._schedule_pre_adjust)
        add("POST", "/api/schedule/rollback", self._schedule_rollback)
        add("POST", "/api/schedule/release", self._schedule_release)
        add("POST", "/api/push", self._push)
        add("POST", "/api/quench", self._quench)
        add("POST", "/api/reverse", self._reverse)
        add("POST", "/api/clean", self._clean)
        add("POST", "/api/calibrate", self._calibrate)
        add("POST", "/api/disturb", self._disturb)
        add("POST", "/api/concurrency", self._concurrency)
        add("POST", "/api/reset", lambda params, body: {"removed": self._platform.reset_state()})

    def routes(self) -> list[dict]:
        """返回接口清单，供自检与文档核对。"""

        return [route.as_dict() for route in self._router.routes()]

    def handle(self, method: str, path: str, query: dict, body: dict) -> tuple[int, dict]:
        """处理一次请求，返回状态码与响应体。"""

        matched = self._router.match(method, path)
        if matched is None:
            return 404, {"error": "not_found", "path": path}
        handler, params = matched
        merged = {**query, **params}
        try:
            payload = handler(merged, body)
        except CokeError as error:
            # 控制台拒绝的动作也要留痕，便于巡检区分"谁触发了哪条联锁"。
            self._platform.note_error(error)
            return 409, {"error": type(error).__name__, **error.as_record()}
        return 200, payload

    def _audit(self, params: dict, body: dict) -> dict:
        limit = int(params.get("limit", 100))
        return {"entries": self._platform.audit.entries(limit=limit)}

    def _events(self, params: dict, body: dict) -> dict:
        topic = params.get("topic")
        return {"events": [event.as_dict() for event in self._platform.bus.history(topic)]}

    def _trend(self, params: dict, body: dict) -> dict:
        signal = params.get("signal", "collector_pressure")
        samples = self._platform.trend.series(signal, limit=int(params.get("limit", 60)))
        filled = self._platform.trend.fill_gaps(signal, samples)
        return {
            "signal": signal,
            "period_s": self._platform.trend.period_s,
            "samples": [sample.as_dict() for sample in filled],
        }

    def _store(self, params: dict, body: dict) -> dict:
        store = self._platform.store
        return {
            "root": store.root,
            "documents": store.list_ids(),
            "platform_state": store.read("platform_state"),
        }

    def _timeline(self, params: dict, body: dict) -> dict:
        oven = params.get("oven")
        records = self._platform.audit.records(limit=int(params.get("limit", 200)))
        return {"timeline": build_timeline(records, oven=oven)}

    def _journal(self, params: dict, body: dict) -> dict:
        journal = self._platform.audit.journal
        payload: dict = {
            "topic": journal.topic,
            "count": journal.count(),
            "active_segment": journal.active_segment(),
            "segments": journal.segments(),
        }
        segment = params.get("segment")
        if segment is not None:
            payload["records"] = self._platform.audit.replay_segment(int(segment))
        return payload

    def _readiness(self, params: dict, body: dict) -> dict:
        platform = self._platform
        checks = {
            "fan_running": platform.dust.is_running(),
            "collector_settled": platform.collector.settled(),
            "audit_writable": platform.audit.summary()["journal_count"] >= 0,
        }
        recent = platform.audit.tail(1)
        info = {
            "flap_latch_engaged": platform.flap.latch.is_engaged(),
            "guide_locked": platform.guide.is_locked(),
            "damper_deg": round(platform.damper.angle_deg, 2),
            "last_audit_ts": recent[-1]["ts"] if recent else None,
        }
        return {"ready": all(checks.values()), "checks": checks, "info": info}

    def _step(self, params: dict, body: dict) -> dict:
        return self._platform.cycle(dt=_as_float(body, "dt", 1.0))

    def _charge(self, params: dict, body: dict) -> dict:
        key = body.get("schedule_key")
        return self._platform.charge(
            oven=str(body.get("oven", "oven01")),
            hopper_target_mm=_as_float(body, "hopper_target_mm", 0.0),
            hopper_measured_mm=_as_float(body, "hopper_measured_mm", 0.0),
            dt=_as_float(body, "dt", 1.0),
            expected_disturbance_pa=_as_float(body, "expected_disturbance_pa", 0.0),
            backflow_risk=bool(body.get("backflow_risk", False)),
            schedule_key=None if key is None else str(key),
        )

    def _schedule_pre_adjust(self, params: dict, body: dict) -> dict:
        key = body.get("key")
        return self._platform.schedule_pre_adjust(
            oven=str(body.get("oven", "oven01")),
            key=None if key is None else str(key),
            expected_disturbance_pa=_as_float(body, "expected_disturbance_pa", 0.0),
            backflow_risk=bool(body.get("backflow_risk", False)),
            dt=_as_float(body, "dt", 1.0),
        )

    def _schedule_rollback(self, params: dict, body: dict) -> dict:
        return self._platform.rollback_pre_adjust(self._require_key(params, body))

    def _schedule_release(self, params: dict, body: dict) -> dict:
        return self._platform.release_pre_adjust(self._require_key(params, body))

    @staticmethod
    def _require_key(params: dict, body: dict) -> str:
        key = body.get("key") or params.get("key")
        if not key:
            raise CokeError("缺少必填字段 'key'", component="console")
        return str(key)

    def _push(self, params: dict, body: dict) -> dict:
        return self._platform.push(
            oven=str(body.get("oven", "oven01")),
            guide_target_mm=_as_float(body, "guide_target_mm", 0.0),
            guide_measured_mm=_as_float(body, "guide_measured_mm", 0.0),
            stroke_target_mm=_as_float(body, "stroke_target_mm", self._platform.stroke.baseline_mm),
            speed_mm_s=_as_float(body, "speed_mm_s", self._platform.config.pusher.speed_default_mm_s),
            dt=_as_float(body, "dt", 1.0),
        )

    def _quench(self, params: dict, body: dict) -> dict:
        return self._platform.quench(
            oven=str(body.get("oven", "oven01")), dt=_as_float(body, "dt", 1.0)
        )

    def _reverse(self, params: dict, body: dict) -> dict:
        temperature = body.get("temperature_c")
        return self._platform.reverse(
            oven=str(body.get("oven", "oven01")),
            temperature_c=None if temperature is None else float(temperature),
        )

    def _clean(self, params: dict, body: dict) -> dict:
        return self._platform.clean(
            oven=str(body.get("oven", "oven01")), dt=_as_float(body, "dt", 1.0)
        )

    def _calibrate(self, params: dict, body: dict) -> dict:
        return self._platform.calibrate_stroke(_as_float(body, "value_mm", self._platform.stroke.baseline_mm))

    def _disturb(self, params: dict, body: dict) -> dict:
        return self._platform.disturb_collector(_as_float(body, "delta_pa", 0.0))

    def _concurrency(self, params: dict, body: dict) -> dict:
        return self._platform.concurrency_probe(rounds=int(body.get("rounds", 24)))
