"""集气管装煤需求调度。

多座炭化室同时装煤会抢同一条集气管：各自为政地调压会互相把压力顶偏，
荒煤气容易倒灌。需求调度层在调压之前先把"谁在装、谁更急"排成一队，
只有排到队的需求才能对集气管预调压力，不再各抢各的。

两条定死的调度规则：

- 优先级按炉况动态算，不按炉号固定：预计扰动越大优先级越高，有倒灌
  风险的炉况再加紧急加成；
- 冲突时紧急炉况插队到全部常规需求之前（紧急档内部按优先级、再按到
  达先后），常规需求之间严格先到先得；正在执行的预调不可中断，插队
  只影响排队顺序。

预调按幂等键去重：同一个键并发重复触发只执行一次，重复触发返回既有
票据，不重复调压、不重复写审计、不改回退基准。每次调度决策带单调时
序号，压力读数、调度票据与审计事件在同一临界区里产生，三者口径一致。
预调失败或后续步骤失败时，压力回退到调压前的值。
"""

from __future__ import annotations

import dataclasses
import threading
from dataclasses import dataclass

from ..clock import Clock
from ..errors import CokeError
from ..eventbus import Event, EventBus
from .collector import CollectorMain

URGENT_BONUS = 1000
MAX_STEPS = 600
TERMINAL_STATUSES = ("released", "rolled_back", "cancelled")


@dataclass(frozen=True)
class OvenCondition:
    """一路装煤需求上报的炉况；调度优先级只由它决定，与炉号无关。"""

    oven: str
    expected_disturbance_pa: float = 0.0
    backflow_risk: bool = False

    @property
    def urgent(self) -> bool:
        """是否属于紧急炉况（有倒灌风险，允许插队）。"""

        return self.backflow_risk

    def priority(self) -> int:
        """按炉况动态计算优先级：预计扰动取整，紧急炉况加紧急加成。"""

        score = int(round(abs(self.expected_disturbance_pa)))
        if self.urgent:
            score += URGENT_BONUS
        return score

    def as_dict(self) -> dict:
        return {
            "oven": self.oven,
            "expected_disturbance_pa": round(self.expected_disturbance_pa, 2),
            "backflow_risk": self.backflow_risk,
            "urgent": self.urgent,
            "priority": self.priority(),
        }


@dataclass(frozen=True)
class DemandTicket:
    """一次登记的装煤需求：排队凭证 + 预调记录（含回退基准）。"""

    key: str
    oven: str
    seq: int
    ts: float
    priority: int
    urgent: bool
    status: str = "queued"
    before_pa: float | None = None
    after_pa: float | None = None

    @property
    def terminal(self) -> bool:
        """票据是否已到终态（释放 / 已回退 / 已取消）。"""

        return self.status in TERMINAL_STATUSES

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "oven": self.oven,
            "seq": self.seq,
            "ts": round(self.ts, 3),
            "priority": self.priority,
            "urgent": self.urgent,
            "status": self.status,
            "before_pa": None if self.before_pa is None else round(self.before_pa, 2),
            "after_pa": None if self.after_pa is None else round(self.after_pa, 2),
        }


class DemandScheduler:
    """装煤需求调度器：登记、排队、预调、回退。"""

    def __init__(
        self,
        collector: CollectorMain,
        clock: Clock,
        bus: EventBus | None = None,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._collector = collector
        self._clock = clock
        self._bus = bus
        self._max_steps = max(1, int(max_steps))
        self._seq = 0
        self._tickets: dict[str, DemandTicket] = {}
        self._lock = threading.RLock()

    def ticket_for(self, key: str) -> DemandTicket | None:
        """按幂等键查票据，不存在返回 ``None``。"""

        with self._lock:
            return self._tickets.get(key)

    def position_of(self, key: str) -> int:
        """返回票据在队列里的位置（1 起）；不在排队返回 0。"""

        with self._lock:
            for position, ticket in enumerate(self._queued_ordered(), start=1):
                if ticket.key == key:
                    return position
            return 0

    def snapshot(self) -> dict:
        """返回调度快照（含定死的调度策略），供控制台展示。"""

        with self._lock:
            queued = self._queued_ordered()
            active = self._active()
            terminal = sorted(
                (ticket for ticket in self._tickets.values() if ticket.terminal),
                key=lambda ticket: ticket.seq,
            )
            return {
                "policy": {
                    "priority": "dynamic_by_condition",
                    "conflict": "urgent_preempts_normal_fcfs",
                    "preemption_scope": "queue_only",
                },
                "queued": [
                    {**ticket.as_dict(), "position": position}
                    for position, ticket in enumerate(queued, start=1)
                ],
                "active": active.as_dict() if active is not None else None,
                "terminal": [ticket.as_dict() for ticket in terminal[-8:]],
                "counts": {
                    "queued": len(queued),
                    "active": 1 if active is not None else 0,
                    "terminal": len(terminal),
                    "issued": self._seq,
                },
            }

    def request(self, key: str, condition: OvenCondition) -> DemandTicket:
        """登记一路装煤需求；同一幂等键重复登记返回原票据，不重复排队。"""

        if not key:
            raise CokeError("幂等键不能为空", component="gas")
        with self._lock:
            existing = self._tickets.get(key)
            if existing is not None:
                return existing
            self._seq += 1
            ticket = DemandTicket(
                key=key,
                oven=condition.oven,
                seq=self._seq,
                ts=self._clock.now(),
                priority=condition.priority(),
                urgent=condition.urgent,
            )
            self._tickets[key] = ticket
            self._publish(
                "demand_queued",
                ticket,
                position=self.position_of(key),
                expected_disturbance_pa=round(condition.expected_disturbance_pa, 2),
            )
            return ticket

    def pre_adjust(self, key: str, dt: float = 1.0) -> DemandTicket:
        """对排到队的需求把压力预调进目标带；同一键重复触发只调一次。

        还没轮到时直接返回当前票据（状态仍为 ``queued``），调用方据此决
        定等待还是放弃；限步内调不进目标带视为预调失败，压力回退到调压
        前的值，票据转为 ``rolled_back``。
        """

        if dt <= 0:
            raise ValueError("步长必须为正")
        with self._lock:
            ticket = self._require(key)
            if ticket.status != "queued":
                # 幂等：已调过或已终结的需求不重复调，原样返回票据。
                return ticket
            if self._active() is not None or ticket.key != self._queued_ordered()[0].key:
                return ticket
            before = self._collector.pressure_pa
            self._publish("demand_granted", ticket, before_pa=round(before, 2))
            steps = 0
            while not self._collector.settled() and steps < self._max_steps:
                self._collector.regulate(dt)
                steps += 1
            if self._collector.settled():
                ticket = self._replace(
                    ticket,
                    status="applied",
                    before_pa=before,
                    after_pa=self._collector.pressure_pa,
                )
                self._publish(
                    "pre_adjust_applied",
                    ticket,
                    steps=steps,
                    before_pa=round(ticket.before_pa, 2),
                    after_pa=round(ticket.after_pa, 2),
                )
            else:
                self._collector.restore(before)
                ticket = self._replace(
                    ticket,
                    status="rolled_back",
                    before_pa=before,
                    after_pa=self._collector.pressure_pa,
                )
                self._publish(
                    "pre_adjust_rolled_back",
                    ticket,
                    severity="warning",
                    reason="not_settled",
                    steps=steps,
                    before_pa=round(ticket.before_pa, 2),
                    after_pa=round(ticket.after_pa, 2),
                )
            return ticket

    def rollback(self, key: str, reason: str = "manual_rollback") -> DemandTicket:
        """把已生效的预调回退到调压前的压力（部分失败用），重复回退幂等。"""

        with self._lock:
            ticket = self._require(key)
            if ticket.status == "applied":
                self._collector.restore(ticket.before_pa)
                ticket = self._replace(
                    ticket, status="rolled_back", after_pa=self._collector.pressure_pa
                )
                self._publish(
                    "pre_adjust_rolled_back",
                    ticket,
                    severity="warning",
                    reason=reason,
                    before_pa=round(ticket.before_pa, 2),
                    after_pa=round(ticket.after_pa, 2),
                )
            elif ticket.status == "queued":
                ticket = self._replace(ticket, status="cancelled")
                self._publish("demand_cancelled", ticket, reason=reason)
            return ticket

    def release(self, key: str) -> DemandTicket:
        """装煤完成，释放调度位；重复释放幂等。"""

        with self._lock:
            ticket = self._require(key)
            if ticket.status == "applied":
                ticket = self._replace(ticket, status="released")
                self._publish("demand_released", ticket)
            elif ticket.status == "queued":
                ticket = self._replace(ticket, status="cancelled")
                self._publish("demand_cancelled", ticket, reason="release_before_grant")
            return ticket

    def _require(self, key: str) -> DemandTicket:
        ticket = self._tickets.get(key)
        if ticket is None:
            raise CokeError(f"未知的调度键 {key!r}", component="gas")
        return ticket

    def _replace(self, ticket: DemandTicket, **changes: object) -> DemandTicket:
        updated = dataclasses.replace(ticket, **changes)
        self._tickets[ticket.key] = updated
        return updated

    def _queued_ordered(self) -> list[DemandTicket]:
        queued = [ticket for ticket in self._tickets.values() if ticket.status == "queued"]
        # 定死：紧急档按优先级再按到达先后排在最前；常规档严格先到先得。
        return sorted(
            queued,
            key=lambda ticket: (
                0 if ticket.urgent else 1,
                -ticket.priority if ticket.urgent else 0,
                ticket.seq,
            ),
        )

    def _active(self) -> DemandTicket | None:
        for ticket in self._tickets.values():
            if ticket.status == "applied":
                return ticket
        return None

    def _publish(
        self, action: str, ticket: DemandTicket, severity: str = "notice", **extra: object
    ) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            Event.of(
                "gas",
                "gas",
                action,
                oven=ticket.oven,
                severity=severity,
                key=ticket.key,
                seq=ticket.seq,
                priority=ticket.priority,
                status=ticket.status,
                **extra,
            )
        )
