"""装煤需求调度器。

多座炭化室同时装煤会争抢集气管压力，互相把压力顶偏、荒煤气倒灌。调度器在
调压律之上加一层需求调度：装煤需求先提交排队，仲裁胜出者获得授权并提前把
压力往目标带下沿预调（给装煤期荒煤气冲击留出上行余量），装煤完成后释放
授权；预调是补偿事务，失败或取消时按同一调节速率回退到调压前的值。

定死的规则（改动必须同步改审计口径）：

* 优先级按炉况动态算，不按炉号固定，公式见 :mod:`coke.dispatch.priority`；
* 冲突仲裁按炉况选模式：队列里有结焦初期需求、或集气管压力越出目标带时，
  按优先级插队（``preempt``，同级按提交序号）；否则严格先到先得（``fcfs``）；
* 集气管是单资源：同一时刻只允许一路需求持有授权，授权释放或回退之后才能
  调度下一路；
* 所有变更操作幂等：同炉重复提交、并发触发预调、重复释放/回退，都返回既有
  记录并带 ``idempotent_replay`` 标记，不重复调压、不重复写流水；
* 每条状态迁移写一条调度流水（全局序号 + 时钟），平台把同一条记录转发审计，
  压力值与记录在同一把锁内读写，压力、调度记录与审计三者一致；重启后从流水
  回放重建调度状态。
"""

from __future__ import annotations

import threading

from ..clock import Clock
from ..config import DispatchLimits
from ..errors import CokeError, InterlockError
from ..gas.collector import CollectorMain
from ..ids import IdFactory
from ..store.journal import JsonlJournal
from .demand import ACTIVE_STATES, DEMAND_STATES, TERMINAL_STATES, ChargeDemand
from .priority import STAGES, priority_of
from .snapshot import DispatchSnapshot

_RECENT_LIMIT = 32


class DemandScheduler:
    """装煤需求调度器（自带流水、幂等语义与重启回放）。"""

    def __init__(
        self,
        clock: Clock,
        collector: CollectorMain,
        limits: DispatchLimits,
        journal: JsonlJournal,
        ids: IdFactory,
    ) -> None:
        self._clock = clock
        self._collector = collector
        self._limits = limits
        self._journal = journal
        self._ids = ids
        self._demands: dict[str, ChargeDemand] = {}
        self._recent: list[dict] = []
        self._seq = 0
        self._lock = threading.RLock()
        self._restore()

    # ------------------------------------------------------------------
    # 内部工具

    def _restore(self) -> None:
        """从落盘流水回放全部迁移，重建需求状态（重启后调度记录不丢）。"""

        for record in self._journal.read_all():
            self._apply_replay(record)

    def _apply_replay(self, record: dict) -> None:
        seq = int(record.get("seq", 0))
        self._seq = max(self._seq, seq)
        event = str(record.get("event", ""))
        demand_id = str(record.get("demand_id", ""))
        if event == "submitted":
            self._demands[demand_id] = ChargeDemand(
                demand_id=demand_id,
                oven=str(record.get("oven", "")),
                stage=str(record.get("stage", "mid")),
                submit_seq=seq,
                submit_ts=float(record.get("ts", 0.0)),
            )
        else:
            demand = self._demands.get(demand_id)
            if demand is not None:
                if event in ("prereg_applied", "prereg_partial"):
                    demand.state = str(record.get("state", demand.state))
                    demand.priority = int(record.get("priority", 0))
                    demand.mode = str(record.get("mode", ""))
                    demand.mode_reason = str(record.get("mode_reason", ""))
                    demand.decided_ts = float(record.get("ts", 0.0))
                    demand.pressure_before_pa = float(record.get("pressure_before_pa", 0.0))
                    demand.prereg_target_pa = float(record.get("prereg_target_pa", 0.0))
                    demand.pressure_after_pa = float(record.get("pressure_after_pa", 0.0))
                    demand.decision_record = dict(record)
                elif event in TERMINAL_STATES:
                    demand.state = str(record.get("state", demand.state))
                    demand.terminal_record = dict(record)
                # rollback_partial 不改变状态，只留流水。
        self._note_recent(record)

    def _note_recent(self, record: dict) -> None:
        self._recent.append(record)
        if len(self._recent) > _RECENT_LIMIT:
            del self._recent[: len(self._recent) - _RECENT_LIMIT]

    def _emit(self, event: str, demand: ChargeDemand, **fields: object) -> dict:
        """把一次状态迁移写入调度流水，返回流水记录。"""

        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": round(self._clock.now(), 3),
            "demand_id": demand.demand_id,
            "oven": demand.oven,
            "event": event,
            "state": demand.state,
            **fields,
        }
        self._journal.append(record)
        self._note_recent(record)
        return record

    def _find_open(self, oven: str) -> ChargeDemand | None:
        for demand in self._demands.values():
            if demand.oven == oven and demand.state not in TERMINAL_STATES:
                return demand
        return None

    def _active(self) -> ChargeDemand | None:
        for demand in self._demands.values():
            if demand.state in ACTIVE_STATES:
                return demand
        return None

    def _must(self, demand_id: str) -> ChargeDemand:
        demand = self._demands.get(demand_id)
        if demand is None:
            raise CokeError(f"未知调度需求 {demand_id!r}", component="dispatch")
        return demand

    def _priority(self, demand: ChargeDemand, now: float) -> int:
        return priority_of(
            demand.stage,
            demand.wait_s(now),
            self._limits.aging_step_s,
            self._limits.aging_max_bonus,
        )

    def _mode(self, queued: list[ChargeDemand]) -> tuple[str, str]:
        """按炉况与压力选仲裁模式（规则定死，见模块文档）。"""

        out_of_band = not self._collector.settled()
        early = any(demand.stage == "early" for demand in queued)
        if out_of_band and early:
            return "preempt", "pressure_out_of_band+early_stage_present"
        if out_of_band:
            return "preempt", "pressure_out_of_band"
        if early:
            return "preempt", "early_stage_present"
        return "fcfs", "calm"

    def _ordered(self, queued: list[ChargeDemand], now: float, mode: str) -> list[ChargeDemand]:
        """按仲裁模式给等待队列排序（快照与实际授权共用同一套顺序）。"""

        if mode == "preempt":
            return sorted(queued, key=lambda d: (-self._priority(d, now), d.submit_seq))
        return sorted(queued, key=lambda d: d.submit_seq)

    # ------------------------------------------------------------------
    # 变更操作（全部幂等）

    def submit(self, oven: str, stage: str) -> dict:
        """提交一路装煤需求；同炉已有未完结需求时幂等回放，不重复排队。"""

        if not oven:
            raise CokeError("炉号不能为空", component="dispatch")
        if stage not in STAGES:
            raise CokeError(f"未知结焦阶段 {stage!r}，可选 {list(STAGES)}", component="dispatch")
        with self._lock:
            existing = self._find_open(oven)
            if existing is not None:
                return {
                    "seq": existing.submit_seq,
                    "ts": round(existing.submit_ts, 3),
                    "demand_id": existing.demand_id,
                    "oven": existing.oven,
                    "event": "submitted",
                    "state": existing.state,
                    "stage": existing.stage,
                    "idempotent_replay": True,
                }
            demand = ChargeDemand(
                demand_id=self._ids.next(),
                oven=oven,
                stage=stage,
                submit_seq=0,
                submit_ts=self._clock.now(),
            )
            record = self._emit("submitted", demand, stage=stage)
            demand.submit_seq = record["seq"]
            self._demands[demand.demand_id] = demand
            return {**record, "submit_seq": record["seq"], "idempotent_replay": False}

    def dispatch(self, dt: float = 1.0) -> dict:
        """仲裁一路排队需求并执行预调。

        已有授权占用集气管时幂等回放该授权（并发触发不会重复调压）；队列为空
        时返回 ``granted=False``。
        """

        with self._lock:
            active = self._active()
            if active is not None:
                assert active.decision_record is not None
                return {**active.decision_record, "granted": True, "idempotent_replay": True}
            queued = sorted(
                (d for d in self._demands.values() if d.state == "queued"),
                key=lambda d: d.submit_seq,
            )
            if not queued:
                return {"granted": False, "idempotent_replay": False}
            now = self._clock.now()
            mode, reason = self._mode(queued)
            winner = self._ordered(queued, now, mode)[0]

            target = self._limits.prereg_target_pa(self._collector.limits)
            before = self._collector.pressure_pa
            steps = 0
            for _ in range(self._limits.prereg_max_steps):
                if self._collector.pressure_pa == target:
                    break
                self._collector.regulate_toward(target, dt)
                steps += 1
            after = self._collector.pressure_pa
            applied = after == target

            winner.state = "applied" if applied else "partial"
            winner.priority = self._priority(winner, now)
            winner.mode = mode
            winner.mode_reason = reason
            winner.decided_ts = now
            winner.pressure_before_pa = before
            winner.prereg_target_pa = target
            winner.pressure_after_pa = after
            record = self._emit(
                "prereg_applied" if applied else "prereg_partial",
                winner,
                stage=winner.stage,
                priority=winner.priority,
                wait_s=round(winner.wait_s(now), 3),
                mode=mode,
                mode_reason=reason,
                contenders=len(queued),
                pressure_before_pa=round(before, 2),
                prereg_target_pa=round(target, 2),
                pressure_after_pa=round(after, 2),
                steps=steps,
            )
            winner.decision_record = record
            return {**record, "granted": True, "idempotent_replay": False}

    def complete(self, demand_id: str) -> dict:
        """装煤完成，释放授权；重复释放幂等回放。"""

        with self._lock:
            demand = self._must(demand_id)
            if demand.state == "released":
                assert demand.terminal_record is not None
                return {**demand.terminal_record, "idempotent_replay": True}
            if demand.state == "rolled_back":
                raise InterlockError("需求已回退，禁止再放行", component="dispatch")
            if demand.state != "applied":
                raise InterlockError("预调未到位，禁止放行装煤", component="dispatch")
            demand.state = "released"
            record = self._emit("released", demand)
            demand.terminal_record = record
            return {**record, "idempotent_replay": False}

    def rollback(self, demand_id: str, dt: float = 1.0) -> dict:
        """把预调回退到调压前的压力；重复回退幂等回放。

        预调属于可部分失败的操作：授权时已记录调压前的压力，需求失败或取消时
        按同一调节速率把压力推回该值。回退未到位（步数预算耗尽）时状态保持
        不变，可再次触发回退。
        """

        with self._lock:
            demand = self._must(demand_id)
            if demand.state == "rolled_back":
                assert demand.terminal_record is not None
                return {**demand.terminal_record, "restored": True, "idempotent_replay": True}
            if demand.state == "released":
                raise InterlockError("需求已放行，禁止回退", component="dispatch")
            if demand.state == "queued":
                raise InterlockError("需求尚未授权预调，无压可回", component="dispatch")
            before = self._collector.pressure_pa
            restore = demand.pressure_before_pa
            steps = 0
            for _ in range(self._limits.prereg_max_steps):
                if self._collector.pressure_pa == restore:
                    break
                self._collector.regulate_toward(restore, dt)
                steps += 1
            after = self._collector.pressure_pa
            fields = {
                "pressure_before_pa": round(before, 2),
                "restore_target_pa": round(restore, 2),
                "pressure_after_pa": round(after, 2),
                "steps": steps,
            }
            if after != restore:
                record = self._emit("rollback_partial", demand, **fields)
                return {**record, "restored": False, "idempotent_replay": False}
            demand.state = "rolled_back"
            record = self._emit("rolled_back", demand, **fields)
            demand.terminal_record = record
            return {**record, "restored": True, "idempotent_replay": False}

    # ------------------------------------------------------------------
    # 只读视图

    def snapshot(self) -> DispatchSnapshot:
        """返回调度快照（控制台展示用），队列顺序与实际授权顺序一致。"""

        with self._lock:
            now = self._clock.now()
            queued = [d for d in self._demands.values() if d.state == "queued"]
            mode, reason = self._mode(queued) if queued else ("fcfs", "calm")
            queued_view = tuple(
                {
                    "demand_id": demand.demand_id,
                    "oven": demand.oven,
                    "stage": demand.stage,
                    "wait_s": round(demand.wait_s(now), 3),
                    "priority": self._priority(demand, now),
                    "submit_seq": demand.submit_seq,
                }
                for demand in self._ordered(queued, now, mode)
            )
            active = self._active()
            active_view = None
            if active is not None:
                active_view = {
                    "demand_id": active.demand_id,
                    "oven": active.oven,
                    "stage": active.stage,
                    "state": active.state,
                    "pressure_before_pa": round(active.pressure_before_pa, 2),
                    "prereg_target_pa": round(active.prereg_target_pa, 2),
                }
            counts = {state: 0 for state in DEMAND_STATES}
            for demand in self._demands.values():
                counts[demand.state] += 1
            return DispatchSnapshot(
                mode=mode,
                mode_reason=reason,
                queued=queued_view,
                active=active_view,
                state_counts=counts,
                recent=tuple(self._recent),
                records_total=self._journal.count(),
            )

    def summary(self) -> dict:
        """返回调度摘要，供平台状态快照引用。"""

        snap = self.snapshot()
        return {
            "mode": snap.mode,
            "queued": len(snap.queued),
            "active": snap.active,
            "records": snap.records_total,
        }
