"""命令行入口。

五个子命令覆盖日常使用：

``serve``   启动控制台 HTTP 服务，可选地在启动后探测接口；
``demo``    在本地跑一遍完整流程（启动 → 装煤 → 换向 → 推焦 → 熄焦 →
            控制周期 → 清扫 → 调度装煤 → 并发探测 → 行程标定），用于交付前的
            真实运行检查；
``status``  打印当前状态快照；
``config``  打印生效配置；
``reset``   清掉落盘的平台计数。
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .app import Platform, build_platform
from .clock import ManualClock, SystemClock
from .config import config_to_mapping, default_config, load_config
from .console.server import ConsoleServer, probe_endpoints
from .errors import CokeError

DEFAULT_PROBE_PATHS = ("/api/status", "/api/readiness", "/api/topology", "/api/audit")


def _build(args: argparse.Namespace) -> Platform:
    config = load_config(args.config) if getattr(args, "config", None) else default_config()
    if getattr(args, "storage_root", None):
        return build_platform(config, storage_root=args.storage_root)
    return Platform(config=config)


def _dump(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _cmd_serve(args: argparse.Namespace) -> int:
    platform = _build(args)
    server = ConsoleServer(platform, host=args.host, port=args.port)
    base_url = server.start()
    payload: dict = {"listening": base_url, "routes": server.api.routes()}
    if args.probe:
        payload["probe"] = probe_endpoints(base_url, list(DEFAULT_PROBE_PATHS))
    _dump(payload)
    if args.duration > 0:
        try:
            time.sleep(args.duration)
        except KeyboardInterrupt:  # pragma: no cover - 交互路径
            pass
        server.stop()
        return 0
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:  # pragma: no cover - 交互路径
        server.stop()
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    clock = ManualClock() if args.fast else SystemClock()
    config_path = getattr(args, "config", None)
    config = load_config(config_path) if config_path else default_config()
    platform = build_platform(config, clock=clock, storage_root=getattr(args, "storage_root", None))
    # 演示从干净基线起步：先清掉上一轮落盘的平台计数。
    platform.reset_state()

    startup = platform.start()
    charge = platform.charge(oven="oven01", hopper_target_mm=0.0, hopper_measured_mm=0.0)
    disturbance = platform.disturb_collector(delta_pa=-45.0)
    clock.advance(config.heating.reversal_interval_s)
    reversal = platform.reverse(oven="oven01", temperature_c=config.heating.temp_target_c)
    push = platform.push(oven="oven01", guide_target_mm=0.0, guide_measured_mm=0.0)
    quench = platform.quench(oven="oven01")
    cycles = [platform.cycle(dt=1.0) for _ in range(8)]
    cleaning = platform.clean(oven="oven01")
    scheduled = platform.charge_scheduled(
        oven="oven02", coking_stage="early", hopper_target_mm=0.0, hopper_measured_mm=0.0
    )
    concurrency = platform.concurrency_probe(rounds=args.rounds)
    calibration = platform.calibrate_stroke(value_mm=3212.0)
    shutdown = platform.stop()

    # 演示自检用临时端口，避免和本机常驻服务抢 8080。
    server = ConsoleServer(platform, port=0)
    base_url = server.start()
    probe = probe_endpoints(base_url, list(DEFAULT_PROBE_PATHS))
    server.stop()

    report = {
        "startup": startup,
        "charge": {"ok": charge["ok"], "steps": [step["action"] for step in charge["steps"]]},
        "disturbance": disturbance,
        "reversal": {"ok": reversal["ok"], "steps": [step["action"] for step in reversal["steps"]]},
        "push": {"ok": push["ok"], "steps": [step["action"] for step in push["steps"]]},
        "quench": {"ok": quench["ok"], "steps": [step["action"] for step in quench["steps"]]},
        "cycles_run": len(cycles),
        "last_cycle": cycles[-1],
        "cleaning": {"ok": cleaning["ok"], "steps": [step["action"] for step in cleaning["steps"]]},
        "charge_scheduled": {
            "ok": scheduled["ok"],
            "mode": scheduled["dispatch"]["decision"].get("mode"),
            "steps": [step["action"] for step in scheduled["steps"]],
        },
        "concurrency": concurrency,
        "calibration": calibration,
        "shutdown": shutdown,
        "probe": probe,
        "audit": platform.audit.summary(),
    }
    _dump(report)
    failures = [name for name, item in probe.items() if not item["ok"]]
    for operation in (charge, reversal, push, quench, cleaning, scheduled):
        if not operation["ok"]:
            failures.extend(operation["violations"])
    if failures:
        print(f"检查未通过: {failures}", file=sys.stderr)
        return 1
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    platform = _build(args)
    payload = platform.status()
    payload["topology"] = platform.topology_summary()
    payload["namespaces"] = platform.namespaces_describe()
    payload["trend"] = platform.trend.snapshot()
    _dump(payload)
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    config_path = getattr(args, "config", None)
    config = load_config(config_path) if config_path else default_config()
    _dump(config_to_mapping(config))
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    platform = _build(args)
    removed = platform.reset_state()
    _dump({"storage_root": platform.store.root, "platform_state_removed": removed})
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。"""

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="JSON 配置文件路径", default=argparse.SUPPRESS)
    common.add_argument("--storage-root", help="覆盖状态存储目录", default=argparse.SUPPRESS)
    parser = argparse.ArgumentParser(
        prog="coke", description="工业顺序控制与联锁服务", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动控制台服务", parents=[common])
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--duration", type=float, default=0.0, help="运行多少秒后退出，0 表示常驻")
    serve.add_argument("--probe", action="store_true", help="启动后探测接口")
    serve.set_defaults(func=_cmd_serve)

    demo = sub.add_parser("demo", help="跑一遍完整流程", parents=[common])
    demo.add_argument("--ovens", type=int, default=1, help="演示的碳化室数量（保留兼容）")
    demo.add_argument("--rounds", type=int, default=24, help="并发探测轮数")
    demo.add_argument("--fast", action="store_true", help="使用可推进时钟，跳过真实等待")
    demo.set_defaults(func=_cmd_demo)

    status = sub.add_parser("status", help="打印状态快照", parents=[common])
    status.set_defaults(func=_cmd_status)

    config = sub.add_parser("config", help="打印生效配置", parents=[common])
    config.set_defaults(func=_cmd_config)

    reset = sub.add_parser("reset", help="清掉落盘的平台计数", parents=[common])
    reset.set_defaults(func=_cmd_reset)
    return parser


def main(argv: list[str] | None = None) -> int:
    """命令行主入口。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CokeError as error:
        print(json.dumps(error.as_record(), ensure_ascii=False), file=sys.stderr)
        return 2
