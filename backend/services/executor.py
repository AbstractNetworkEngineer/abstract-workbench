"""统一命令执行器：优先活动终端会话，回退新建连接。

ok 的含义是"设备接受了这条命令"，而不是"命令发出去了"。
设备用错误文案拒绝命令（% Invalid input 等）时 ok 必须为 False，
否则变更闸门会把"设备拒绝"显示成"执行成功"。
"""

from connectors import ConnectorError, connector_from_device, get_dialect
from services.cli_errors import judge_command
from services.session_hub import get_live_session
from services.session_setup import prepare_session


def execute_on_device(device, commands: list[str], timeout_each: float = 15.0):
    """返回 (results, via)。results: [{command, output, ok, error?}]"""
    commands = [c.strip() for c in commands if c.strip()]
    if not commands:
        return [], "none"

    live = get_live_session(device.id)
    if live is not None:
        return live.run_commands(commands, timeout_each), "live-session"

    results = []
    with connector_from_device(device) as conn:
        prepare_session(conn, get_dialect(device.vendor))
        for cmd in commands:
            try:
                out = conn.run(cmd, timeout=timeout_each)
            except Exception as e:  # noqa: BLE001
                results.append({"command": cmd, "output": str(e), "ok": False,
                                "error": f"执行异常：{e}"})
                break
            results.append(judge_command(cmd, out))
    return results, "new-connection"


def serial_hint(device) -> str:
    if device.protocol == "serial":
        return "（串口为独占资源：若终端正连接该设备，配置写入会自动复用活动会话）"
    return ""
