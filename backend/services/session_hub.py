"""活动会话中心：配置写入复用终端已建立的会话执行命令。

串口（Serial）是独占资源 —— 终端会话占着 COM 口时，另开连接必然失败
（Windows 报"拒绝访问"，被误认为断链）。因此配置写入优先走活动会话，
命令同时实时回显在终端里，操作者眼见为实。
"""

import logging
import threading
import time

from connectors.base import strip_ansi
from services.cli_errors import judge_command

logger = logging.getLogger("netdeck.session_hub")

_registry: dict[int, "LiveSession"] = {}
_registry_lock = threading.Lock()


class LiveSession:
    def __init__(self, connector, device_id: int | None = None):
        self.connector = connector
        self.device_id = device_id
        self._lock = threading.Lock()
        self._capture_sink: list[str] | None = None

    # ---- 由 WS 泵调用（事件循环线程） ----
    def on_chunk(self, chunk: str) -> None:
        with self._lock:
            if self._capture_sink is not None:
                self._capture_sink.append(chunk)

    # ---- 由配置写入调用（工作线程） ----
    def run_commands(self, commands: list[str], timeout_each: float = 15.0) -> list[dict]:
        """按顺序执行命令并采集输出。流式会话走通道捕获；否则直接 run()。"""
        results = []
        if not getattr(self.connector, "supports_stream", False):
            for cmd in commands:
                try:
                    out = self.connector.run(cmd, timeout=timeout_each)
                except Exception as e:  # noqa: BLE001
                    results.append({"command": cmd, "output": str(e), "ok": False,
                                    "error": f"执行异常：{e}"})
                    break
                results.append(judge_command(cmd, out))
            return results

        with self._lock:
            for cmd in commands:
                sink: list[str] = []
                self._capture_sink = sink
                try:
                    self.connector.write_raw(cmd + self.connector.line_ending)
                except Exception as e:  # noqa: BLE001
                    self._capture_sink = None
                    results.append({"command": cmd, "output": str(e), "ok": False,
                                    "error": f"执行异常：{e}"})
                    break

                # 等待输出稳定（连续 0.7s 无新数据视为该命令结束）
                deadline = time.time() + timeout_each
                last_size, quiet_since = -1, time.time()
                while time.time() < deadline:
                    time.sleep(0.15)
                    size = sum(len(x) for x in sink)
                    if size != last_size:
                        last_size = size
                        quiet_since = time.time()
                        continue
                    if size > 0 and time.time() - quiet_since > 0.7:
                        break
                    if size == 0 and time.time() - quiet_since > 1.5:
                        break

                self._capture_sink = None
                raw = "".join(sink)
                results.append(judge_command(cmd, strip_ansi(raw).strip()))
        return results


def register(session: LiveSession) -> None:
    if session.device_id is None:
        return
    with _registry_lock:
        _registry[session.device_id] = session


def unregister(device_id: int | None) -> None:
    if device_id is None:
        return
    with _registry_lock:
        _registry.pop(device_id, None)


def get_live_session(device_id: int) -> LiveSession | None:
    with _registry_lock:
        return _registry.get(device_id)
