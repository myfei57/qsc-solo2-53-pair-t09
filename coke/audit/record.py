"""审计记录。

一条记录固定携带时间、碳化室号、组件、动作、严重度和说明，附带可选的上下
文字段。严重度分三档：``notice``（正常动作）、``warning``（可恢复异常）、
``alarm``（联锁拒绝或越限），控制台的告警页只取后两档。
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITIES = ("notice", "warning", "alarm")


@dataclass(frozen=True)
class AuditRecord:
    """一条审计流水。"""

    ts: float
    oven: str
    component: str
    action: str
    severity: str
    message: str
    payload: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        ts: float,
        oven: str,
        component: str,
        action: str,
        severity: str = "notice",
        message: str = "",
        **payload: object,
    ) -> "AuditRecord":
        if severity not in SEVERITIES:
            severity = "notice"
        return cls(ts, oven, component, action, severity, message, dict(payload))

    @classmethod
    def from_dict(cls, raw: dict) -> "AuditRecord":
        """从落盘字段还原一条记录。"""

        return cls(
            ts=float(raw.get("ts", 0.0)),
            oven=str(raw.get("oven", "")),
            component=str(raw.get("component", "")),
            action=str(raw.get("action", "")),
            severity=str(raw.get("severity", "notice")),
            message=str(raw.get("message", "")),
            payload=dict(raw.get("payload", {})),
        )

    def as_dict(self) -> dict:
        return {
            "ts": round(self.ts, 3),
            "oven": self.oven,
            "component": self.component,
            "action": self.action,
            "severity": self.severity,
            "message": self.message,
            "payload": self.payload,
        }

    def is_alarm(self) -> bool:
        """是否属于告警档（warning / alarm）。"""

        return self.severity in ("warning", "alarm")
