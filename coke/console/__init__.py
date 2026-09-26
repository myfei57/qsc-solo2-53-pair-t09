"""控制台 HTTP 服务。

纯 JSON 接口，不含前端页面：路由把 ``/api/...`` 映射到平台的状态查询与动作
接口，服务用标准库 ``http.server`` 承载。控制台只调用平台暴露的公开方法，
不直接碰任何组件私有状态。
"""

from __future__ import annotations

from .api import Api
from .router import Router, Route
from .server import ConsoleServer, probe_endpoints

__all__ = ["Api", "Router", "Route", "ConsoleServer", "probe_endpoints"]
