"""平台装配与控制循环。

``Platform`` 把各组件按真实调用链接起来，并暴露四件事：操作编排（装煤、
推焦、熄焦、换向、炉门清扫，以及带需求调度的装煤）、控制循环、并发仲裁
探测和状态快照。控制循环每个周期做三件事：把集气管压力调向目标带、按推焦
联动时序驱动除尘挡板、采集趋势；换向与推焦这类跨模块动作都由编排一次性走
完并写审计。多炉同时装煤时由需求调度层先仲裁授权、预调集气管压力，再进入
装煤编排。
"""

from __future__ import annotations

import dataclasses
import threading

from .audit.log import AuditLog
from .audit.record import AuditRecord
from .charger.machine import ChargingCar
from .clock import Clock, SystemClock
from .config import PlatformConfig, default_config
from .dispatch.scheduler import DemandScheduler
from .door.latch import DoorLatch
from .door.machine import DoorCleaner
from .dust.damper import DustDamper
from .dust.schedule import DamperSchedule
from .dust.snapshot import DustSnapshot
from .dust.system import DustSystem
from .errors import CokeError
from .eventbus import Event, EventBus
from .gas.collector import CollectorMain
from .gas.flap import BridgeFlap
from .gas.latch import FlapLatch
from .guide.machine import GuideCar
from .heating.machine import HeatingReversal
from .heating.snapshot import HeatingSnapshot
from .heating.temperature import OvenTemperature
from .heating.valvetrain import ValveTrain
from .ids import IdFactory
from .ns.registry import NamespaceRegistry
from .ns.topology import Topology, build_default_topology
from .pusher.machine import PusherMachine
from .pusher.speed import SpeedArbiter
from .pusher.stroke import StrokeBaseline
from .quench.machine import QuenchCar
from .sequence import charge_oven, clean_door, push_oven, quench_oven, reverse_heating
from .store.journal import JsonlJournal
from .store.jsonfile import JsonStore
from .telemetry import TrendBuffer

DEFAULT_UNIT = "battery1"
DEFAULT_OVEN = "oven01"

_DISPATCH_MESSAGES = {
    "submitted": "装煤需求已提交",
    "prereg_applied": "预调到位，授权装煤",
    "prereg_partial": "预调未到位（部分失败）",
    "released": "装煤完成，释放调度授权",
    "rolled_back": "预调已回退到调压前的值",
    "rollback_partial": "回退未到位",
}


class Platform:
    """焦炉推装熄顺序控制平台。"""

    def __init__(
        self,
        config: PlatformConfig | None = None,
        clock: Clock | None = None,
        unit: str = DEFAULT_UNIT,
    ) -> None:
        self.config = config or default_config()
        self.clock = clock or SystemClock()
        self.bus = EventBus()
        self.unit = unit

        store = JsonStore(self.config.storage_root)
        self.store = store
        self.audit = AuditLog(self.clock, self.bus, JsonlJournal(store.root, "audit", segment_limit=512))
        self.namespaces = NamespaceRegistry(unit)
        self.topology: Topology = build_default_topology()
        self.trend = TrendBuffer(period_s=5.0)
        self.ids = IdFactory("op")

        self.pusher = PusherMachine(self.config.pusher)
        self.stroke = StrokeBaseline(
            self.config.pusher.stroke_baseline_mm, self.config.pusher.stroke_tolerance_mm
        )
        self.speed = SpeedArbiter(
            self.config.pusher.speed_min_mm_s,
            self.config.pusher.speed_max_mm_s,
            self.config.pusher.speed_default_mm_s,
        )
        self.guide = GuideCar(self.config.guide)
        self.charger = ChargingCar(self.config.charger)
        self.quench_car = QuenchCar(self.config.quench)
        self.collector = CollectorMain(self.config.collector)
        self.flap = BridgeFlap(FlapLatch())
        self.dispatcher = DemandScheduler(
            self.clock,
            self.collector,
            self.config.dispatch,
            JsonlJournal(store.root, "dispatch", segment_limit=512),
            IdFactory("dm"),
        )
        self.door = DoorCleaner(self.config.door, DoorLatch(self.config.door.latch_travel_mm))
        self.reversal = HeatingReversal(self.config.heating, self.clock)
        self.valves = ValveTrain()
        self.temperature = OvenTemperature(self.config.heating)
        self.dust = DustSystem()
        self.damper = DustDamper(self.config.dust.damper_open_deg, self.config.dust.damper_rate_deg_per_s)
        self.schedule = DamperSchedule(self.config.dust.linkage_lag_s)

        self._cycles = 0
        self._operations = 0
        self._lock = threading.RLock()
        self._register_namespaces()
        self._restore()

    def _register_namespaces(self) -> None:
        """登记现场设备命名空间（控制台与审计共用同一套名字）。"""

        for area, device, kind in (
            ("battery", "pusher", "pusher-machine"),
            ("battery", "guide", "guide-car"),
            ("battery", "charger", "charging-car"),
            ("battery", "quench", "quench-car"),
            ("battery", "collector", "collector-main"),
            ("battery", "bridge_flap", "bridge-flap"),
            ("battery", "dispatch", "demand-scheduler"),
            ("battery", "door", "door-cleaner"),
            ("battery", "reversal", "reversing-valve"),
            ("battery", "dust", "dust-damper"),
        ):
            self.namespaces.register(area, device, kind)

    def _restore(self) -> None:
        """从落盘审计回放最后一次换向，恢复换向间隔计时。"""

        try:
            records = self.audit.to_records(self.audit.replay_from_journal(limit=100_000))
        except CokeError:
            return
        reversals = [item for item in records if item.action == "reverse_complete"]
        # 只接受不晚于当前时钟的回放记录；可推进时钟重置后，上一轮留下的未来
        # 时间戳属于过期状态，不能拿它把换向间隔计时顶到当前时刻之前。
        if reversals and reversals[-1].ts <= self.clock.now():
            self.reversal.mark_reversed(reversals[-1].ts)
        state = self.store.read("platform_state")
        if isinstance(state, dict):
            self._operations = int(state.get("operations", 0))
            self._cycles = int(state.get("cycles", 0))

    def _persist(self) -> None:
        """落盘平台计数，供重启后对照。"""

        self.store.write(
            "platform_state",
            {"operations": self._operations, "cycles": self._cycles, "unit": self.unit},
        )

    def _record_operation(self, op_id: str, operation: str, report: dict) -> dict:
        """把编排步骤逐条写审计，并记一条汇总事件。"""

        oven = str(report.get("oven", ""))
        for step in report.get("steps", []):
            detail = {
                key: value
                for key, value in step.get("detail", {}).items()
                if not isinstance(value, (dict, list))
                and key not in ("oven", "op_id", "severity", "message")
            }
            self.bus.publish(
                Event.of(
                    step["component"],
                    step["component"],
                    step["action"],
                    oven=oven,
                    op_id=op_id,
                    severity="notice",
                    **detail,
                )
            )
        for violation in report.get("violations", []):
            self.bus.publish(
                Event.of(
                    "audit",
                    "audit",
                    "interlock_rejected",
                    oven=oven,
                    op_id=op_id,
                    severity="alarm",
                    message=f"{operation} 被拒绝：{violation}",
                    violation=violation,
                )
            )
        summary = {
            "op_id": op_id,
            "operation": operation,
            "oven": oven,
            "ok": bool(report.get("ok")),
            "violations": list(report.get("violations", [])),
        }
        self.bus.publish(
            Event.of(
                "audit",
                "audit",
                f"{operation}_complete",
                severity="notice" if report.get("ok") else "warning",
                message=f"{operation} 完成" if report.get("ok") else f"{operation} 未完成",
                **summary,
            )
        )
        return summary

    def _finish_operation(self, op_id: str, operation: str, report: dict) -> dict:
        """写审计、累计计数并落盘，返回合并后的操作报告。"""

        summary = self._record_operation(op_id, operation, report)
        summary["op_id"] = op_id
        self._operations += 1
        self._persist()
        return {**report, **summary}

    def _audit_dispatch(self, op_id: str, record: dict) -> None:
        """把一条调度流水同步到审计（幂等回放不重复落审计）。"""

        event = str(record.get("event", ""))
        if record.get("idempotent_replay") or not event:
            return
        detail = {
            key: value
            for key, value in record.items()
            if key not in ("ts", "oven", "event", "idempotent_replay", "granted", "restored")
            and not isinstance(value, (dict, list))
        }
        self.bus.publish(
            Event.of(
                "dispatch",
                "dispatch",
                event,
                oven=str(record.get("oven", "")),
                op_id=op_id,
                severity="warning" if event in ("prereg_partial", "rollback_partial") else "notice",
                message=_DISPATCH_MESSAGES.get(event, event),
                **detail,
            )
        )

    def start(self) -> dict:
        """启动平台：启动除尘风机并核对拓扑。"""

        with self._lock:
            self.dust.start()
            report = self.topology.verify(set())
            return {
                "fan_running": self.dust.is_running(),
                "topology_missing": report["missing"],
                "operations": self._operations,
            }

    def stop(self) -> dict:
        """停运平台：停除尘风机。"""

        with self._lock:
            self.dust.stop()
            return {"fan_running": self.dust.is_running(), "operations": self._operations}

    def charge(
        self,
        oven: str = DEFAULT_OVEN,
        hopper_target_mm: float = 0.0,
        hopper_measured_mm: float = 0.0,
        dt: float = 1.0,
    ) -> dict:
        """装煤编排：煤斗对位 → 调压 → 开翻板 → 给煤。"""

        with self._lock:
            op_id = self.ids.next()
            report = charge_oven(
                self.charger, self.collector, self.flap, oven, hopper_target_mm, hopper_measured_mm, dt
            )
            return self._finish_operation(op_id, "charge", report)

    def push(
        self,
        oven: str = DEFAULT_OVEN,
        guide_target_mm: float = 0.0,
        guide_measured_mm: float = 0.0,
        stroke_target_mm: float | None = None,
        speed_mm_s: float | None = None,
        dt: float = 1.0,
    ) -> dict:
        """推焦编排：导焦栅对位 → 锁定 → 推焦 → 退杆；同时触发除尘联动。"""

        with self._lock:
            op_id = self.ids.next()
            target = self.stroke.baseline_mm if stroke_target_mm is None else stroke_target_mm
            self.speed.request("auto_cycle", speed_mm_s or self.config.pusher.speed_default_mm_s, priority=50)
            arbitration = self.speed.resolve()
            self.schedule.start_link(self.clock.now())
            report = push_oven(
                self.pusher,
                self.guide,
                oven,
                guide_target_mm,
                guide_measured_mm,
                target,
                arbitration.speed_mm_s,
                dt,
            )
            stroke_check = self.stroke.check(self.pusher.ram_mm)
            report["speed_arbitration"] = arbitration.as_dict()
            report["stroke_check"] = stroke_check
            return self._finish_operation(op_id, "push", report)

    def quench(self, oven: str = DEFAULT_OVEN, dt: float = 1.0) -> dict:
        """熄焦编排：接焦 → 走行 → 喷淋。"""

        with self._lock:
            op_id = self.ids.next()
            report = quench_oven(self.quench_car, oven, dt)
            report["travel_eta_s"] = self.quench_car.plan.eta_s()
            return self._finish_operation(op_id, "quench", report)

    def reverse(self, oven: str = DEFAULT_OVEN, temperature_c: float | None = None) -> dict:
        """换向编排：废气阀 → 煤气阀 → 炉温确认。"""

        with self._lock:
            op_id = self.ids.next()
            target_temp = self.config.heating.temp_target_c if temperature_c is None else temperature_c
            report = reverse_heating(self.reversal, self.valves, self.temperature, oven, target_temp)
            report["offset_c"] = self.temperature.offset_c()
            return self._finish_operation(op_id, "reverse", report)

    def clean(self, oven: str = DEFAULT_OVEN, dt: float = 1.0) -> dict:
        """炉门清扫编排：松开闩锁 → 开炉门 → 清扫 → 复位闩锁。"""

        with self._lock:
            op_id = self.ids.next()
            report = clean_door(self.door, oven, dt)
            return self._finish_operation(op_id, "clean", report)

    def submit_charge_demand(self, oven: str = DEFAULT_OVEN, coking_stage: str = "mid") -> dict:
        """提交一路装煤需求（同炉重复提交幂等，返回既有需求）。"""

        with self._lock:
            op_id = self.ids.next()
            record = self.dispatcher.submit(oven, coking_stage)
            self._audit_dispatch(op_id, record)
            return record

    def dispatch_next(self, dt: float = 1.0) -> dict:
        """仲裁一路排队需求并执行预调（并发重复触发幂等，不重复调压）。"""

        with self._lock:
            op_id = self.ids.next()
            record = self.dispatcher.dispatch(dt)
            self._audit_dispatch(op_id, record)
            return record

    def complete_charge_demand(self, demand_id: str) -> dict:
        """装煤完成，释放调度授权（重复释放幂等）。"""

        with self._lock:
            op_id = self.ids.next()
            record = self.dispatcher.complete(demand_id)
            self._audit_dispatch(op_id, record)
            return record

    def rollback_charge_demand(self, demand_id: str, dt: float = 1.0) -> dict:
        """把预调回退到调压前的压力（重复回退幂等）。"""

        with self._lock:
            op_id = self.ids.next()
            record = self.dispatcher.rollback(demand_id, dt)
            self._audit_dispatch(op_id, record)
            return record

    def charge_scheduled(
        self,
        oven: str = DEFAULT_OVEN,
        coking_stage: str = "mid",
        hopper_target_mm: float = 0.0,
        hopper_measured_mm: float = 0.0,
        dt: float = 1.0,
    ) -> dict:
        """调度装煤编排：提交需求 → 仲裁预调 → 装煤 → 释放；失败回退预调。

        与 :meth:`charge` 的差别在于压力先经需求调度授权并预调到位；预调属于
        可部分失败的操作，预调未到位或装煤编排失败都会把压力回退到调压前的值。
        """

        with self._lock:
            op_id = self.ids.next()
            submit = self.dispatcher.submit(oven, coking_stage)
            self._audit_dispatch(op_id, submit)
            decision = self.dispatcher.dispatch(dt)
            self._audit_dispatch(op_id, decision)
            dispatch_info = {"submit": submit, "decision": decision}

            if not decision.get("granted", False):
                report = {
                    "oven": oven,
                    "ok": False,
                    "steps": [],
                    "violations": ["dispatch_queue_empty"],
                    "dispatch": dispatch_info,
                }
                return self._finish_operation(op_id, "charge_scheduled", report)
            if decision["demand_id"] != submit["demand_id"]:
                report = {
                    "oven": oven,
                    "ok": False,
                    "steps": [],
                    "violations": ["dispatch_not_granted"],
                    "dispatch": dispatch_info,
                }
                return self._finish_operation(op_id, "charge_scheduled", report)
            if decision["state"] == "partial":
                rollback = self.dispatcher.rollback(decision["demand_id"], dt)
                self._audit_dispatch(op_id, rollback)
                report = {
                    "oven": oven,
                    "ok": False,
                    "steps": [],
                    "violations": ["prereg_partial"],
                    "dispatch": dispatch_info,
                    "rollback": rollback,
                }
                return self._finish_operation(op_id, "charge_scheduled", report)

            report = charge_oven(
                self.charger, self.collector, self.flap, oven, hopper_target_mm, hopper_measured_mm, dt
            )
            report["dispatch"] = dispatch_info
            if report["ok"]:
                release = self.dispatcher.complete(decision["demand_id"])
                self._audit_dispatch(op_id, release)
                report["release"] = release
            else:
                rollback = self.dispatcher.rollback(decision["demand_id"], dt)
                self._audit_dispatch(op_id, rollback)
                report["rollback"] = rollback
            return self._finish_operation(op_id, "charge_scheduled", report)

    def dispatch_snapshot(self) -> dict:
        """调度快照：仲裁模式、等待队列、当前授权与最近调度流水。"""

        return self.dispatcher.snapshot().as_dict()

    def cycle(self, dt: float = 1.0) -> dict:
        """推进一个控制周期，返回本周期摘要。"""

        if dt <= 0:
            raise ValueError("步长必须为正")
        with self._lock:
            self._cycles += 1
            moment = self.clock.now()
            before = self.collector.pressure_pa
            pressure = self.collector.regulate(dt)
            linkage = self.schedule.due(moment)
            target_deg = self.damper.open_deg if self.schedule.links() else 0.0
            angle = self.damper.drive_to(target_deg, dt)
            if self.damper.at_open():
                self.schedule.clear()
            self.trend.append("collector_pressure", moment, pressure)
            self.trend.append("damper_angle", moment, angle)
            self._persist()
            return {
                "cycle": self._cycles,
                "pressure_pa": round(pressure, 2),
                "pressure_delta": round(pressure - before, 3),
                "settled": self.collector.settled(),
                "damper_deg": round(angle, 2),
                "linkage_due": linkage,
                "linkage_elapsed_s": round(self.schedule.elapsed_s(moment), 2),
            }

    def concurrency_probe(self, rounds: int = 24) -> dict:
        """用真实并行调用探测推焦速度仲裁的收敛结果。

        两个线程分别代表自动循环与手动控制台，同时向推焦杆提交速度。探测只
        读取最终提交值，用来确认共享执行器始终收敛到唯一值。
        """

        if rounds < 1:
            raise ValueError("探测轮数必须为正")

        def worker(writer: str, speed: float, priority: int) -> None:
            for _ in range(rounds):
                self.speed.request(writer, speed, priority)

        threads = [
            threading.Thread(target=worker, args=("auto_cycle", self.config.pusher.speed_max_mm_s, 50)),
            threading.Thread(target=worker, args=("manual_console", self.config.pusher.speed_min_mm_s, 80)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        outcome = self.speed.resolve()
        self.pusher.set_speed(outcome.speed_mm_s)
        return {
            "rounds": rounds,
            "winner": outcome.winner,
            "committed_mm_s": round(outcome.speed_mm_s, 2),
            "contenders": outcome.contenders,
            "writers": self.speed.writers(),
            "committed_on_machine": round(self.pusher.committed_speed(), 2),
        }

    def calibrate_stroke(self, value_mm: float) -> dict:
        """重新标定推焦行程基线，返回标定前后的差值。"""

        if value_mm <= 0:
            raise CokeError("标定值必须为正", component="pusher")
        before = self.stroke.baseline_mm
        after = self.stroke.calibrate(value_mm)
        self.bus.publish(
            Event.of(
                "pusher",
                "pusher",
                "stroke_recalibrated",
                severity="notice",
                baseline_before_mm=before,
                baseline_after_mm=after,
                epoch=self.stroke.epoch,
            )
        )
        return {"before_mm": before, "after_mm": after, "epoch": self.stroke.epoch}

    def disturb_collector(self, delta_pa: float) -> dict:
        """模拟一次集气管扰动，返回扰动后压力。"""

        before = self.collector.pressure_pa
        after = self.collector.disturb(delta_pa)
        return {"before_pa": round(before, 2), "after_pa": round(after, 2), "settled": self.collector.settled()}

    def note_error(self, error: CokeError) -> dict:
        """把平台异常写入审计，返回落盘记录。"""

        payload = error.as_record()
        record = self.audit.record(
            AuditRecord.create(
                self.clock.now(),
                "",
                payload["component"],
                "error",
                severity="warning",
                message=payload["message"],
            )
        )
        return record

    def reset_state(self) -> bool:
        """清掉落盘的平台计数（交付前重新标定用）。"""

        if not self.store.exists("platform_state"):
            return False
        return self.store.remove("platform_state")

    def heating_snapshot(self) -> HeatingSnapshot:
        """返回加热换向状态快照。"""

        return HeatingSnapshot(
            waste_gas_open=self.valves.waste_open,
            gas_open=self.valves.gas_open,
            temperature_c=self.temperature.value_c,
            confirmed=self.temperature.confirmed(),
            reversals=self.reversal.count(),
            seconds_to_due=self.reversal.seconds_to_due(),
        )

    def dust_snapshot(self) -> DustSnapshot:
        """返回除尘状态快照。"""

        return DustSnapshot(
            fan_running=self.dust.is_running(),
            damper_deg=self.damper.angle_deg,
            damper_open=self.damper.at_open(),
            linkage_pending=self.schedule.links() > 0,
            links=self.schedule.links(),
        )

    def topology_summary(self) -> dict:
        """返回工艺链拓扑摘要。"""

        return self.topology.summary()

    def namespaces_describe(self) -> dict:
        """返回命名空间摘要。"""

        return self.namespaces.describe()

    def status(self) -> dict:
        """汇总状态快照，供控制台与命令行读取。"""

        return {
            "platform": self.config.name,
            "unit": self.unit,
            "operations": self._operations,
            "cycles": self._cycles,
            "now": round(self.clock.now(), 3),
            "utc": self.clock.utc_iso(),
            "pusher": self.pusher.snapshot().as_dict(),
            "speed": {"committed_mm_s": round(self.speed.committed(), 2)},
            "stroke": {
                "baseline_mm": self.stroke.baseline_mm,
                "tolerance_mm": self.stroke.tolerance_mm,
                "epoch": self.stroke.epoch,
            },
            "guide": self.guide.snapshot().as_dict(),
            "charger": self.charger.snapshot().as_dict(),
            "quench": self.quench_car.snapshot().as_dict(),
            "gas": {
                "pressure_pa": round(self.collector.pressure_pa, 2),
                "target_pa": self.collector.limits.pressure_target_pa,
                "settled": self.collector.settled(),
                "flap_deg": round(self.flap.angle_deg, 2),
                "flap_open": self.flap.is_open(),
                "latch_engaged": self.flap.latch.is_engaged(),
                "latch_cycles": self.flap.latch.cycles(),
                "latch_resets": self.flap.latch.resets(),
            },
            "dispatch": self.dispatcher.summary(),
            "door": {**self.door.snapshot().as_dict(), "latch_cycles": self.door.latch.cycles()},
            "heating": self.heating_snapshot().as_dict(),
            "dust": self.dust_snapshot().as_dict(),
            "dust_starts": self.dust.starts(),
            "audit": self.audit.summary(),
            "ids_issued": self.ids.issued(),
        }

    def snapshot(self) -> dict:
        """返回只读的整体快照（状态 + 拓扑 + 命名空间 + 趋势）。"""

        return {
            "status": self.status(),
            "topology": self.topology_summary(),
            "namespaces": self.namespaces_describe(),
            "trend": self.trend.snapshot(),
        }


def build_platform(
    config: PlatformConfig | None = None,
    clock: Clock | None = None,
    storage_root: str | None = None,
    unit: str = DEFAULT_UNIT,
) -> Platform:
    """构造一个平台；``storage_root`` 可覆盖配置里的存储目录。"""

    base = config or default_config()
    if storage_root is not None:
        base = dataclasses.replace(base, storage_root=storage_root)
    return Platform(base, clock=clock, unit=unit)
