"""推焦机。

推焦机负责炭化室内的推焦行程：先把推焦杆按速度指令送到行程基线，炭化室内
焦炭被推出后按退杆指令返回。推焦杆速度由两个写入方竞争（自动循环与手动
控制台），先经仲裁器收敛成唯一提交速度再驱动。
"""

from __future__ import annotations

from .machine import PusherMachine
from .snapshot import PusherSnapshot
from .speed import SpeedArbiter, SpeedOutcome
from .stroke import StrokeBaseline

__all__ = ["PusherMachine", "PusherSnapshot", "SpeedArbiter", "SpeedOutcome", "StrokeBaseline"]
