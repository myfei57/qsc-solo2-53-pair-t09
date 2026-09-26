"""平台统一异常类型。

现场必须区分三类失败：联锁条件不满足（运行期可恢复，条件满足即可继续）、
对齐超差（机械位置没到位，需要重新定位）、配置或持久化失败（装配期就要
拦下的接线问题）。审计日志按异常类型分别落盘，巡检时才能一眼区分"条件
没到"、"没对好位"和"接线不对"。
"""

from __future__ import annotations


class CokeError(Exception):
    """所有平台异常的基类，携带出错的组件名。"""

    def __init__(self, message: str, *, component: str = "coke") -> None:
        super().__init__(message)
        self.message = message
        self.component = component

    def as_record(self) -> dict:
        """转成审计日志可以直接落盘的一条记录。"""

        return {
            "type": type(self).__name__,
            "component": self.component,
            "message": self.message,
        }


class InterlockError(CokeError):
    """联锁条件不满足，动作被拒绝。"""


class AlignmentError(CokeError):
    """机械位置超出对齐公差。"""


class StorageError(CokeError):
    """持久化读写失败。"""


class ConfigError(CokeError):
    """配置缺失或取值非法。"""


class NamespaceError(CokeError):
    """命名空间重复注册或解析失败。"""
