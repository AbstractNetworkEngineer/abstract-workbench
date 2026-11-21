"""WebSocket 终端会话：工作台实时交互通道（带 Origin + 令牌双校验）。

通道 IO 走单线程执行器（max_workers=1），保证按键按下的顺序写入设备 ——
通用线程池并发写会把字符顺序打乱（典型现象："show" 敲成 "shwo"）。
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from connectors import ConnectorError, connector_from_device, create_connector, get_dialect
from database import SessionLocal
from models import Device
from services.security import get_token, origin_ok
from services.session_hub import LiveSession, register as hub_register, unregister as hub_unregister
from services.session_setup import prepare_session

logger = logging.getLogger("netdeck.ws")
router = APIRouter()

HTTP_PORT = int(os.environ.get("ABSTRACT_WORKBENCH_PORT", "18765"))


@router.websocket("/ws/session")
async def session(
    websocket: WebSocket,
    device_id: int | None = Query(default=None),
    protocol: str | None = Query(default=None),
    host: str | None = Query(default=None),
    port: int | None = Query(default=None),
    username: str | None = Query(default=None),
    password: str | None = Query(default=None),
    serial_port: str | None = Query(default=None),
    baudrate: int | None = Query(default=None),
    vendor: str | None = Query(default=None),
    encoding: str | None = Query(default=None),
    token: str | None = Query(default=None),
):
    # 安全闸：浏览器必须同源，脚本必须携带正确令牌
    origin = websocket.headers.get("origin")
    if origin is not None:
        if not origin_ok(origin, HTTP_PORT):
            await websocket.close(code=4403)
            return
    elif not token or token != get_token():
        await websocket.close(code=4401)
        return

    await websocket.accept()

    db: Session = SessionLocal()
    connector = None
    dialect = None
    live: LiveSession | None = None
    io_pool = ThreadPoolExecutor(max_workers=1)  # 按键/读取严格串行，保序
    loop = asyncio.get_event_loop()
    try:
        # 1. 构建连接器
        if device_id:
            device = db.get(Device, device_id)
            if device is None:
                await websocket.send_json({"type": "error", "data": "设备不存在"})
                await websocket.close()
                return
            connector = connector_from_device(device)
            dialect = get_dialect(device.vendor)
            label = f"{device.name} ({device.protocol}://{device.host or device.serial_port})"
        else:
            connector = create_connector(
                protocol=protocol or "ssh",
                host=host or "",
                port=port or 22,
                username=username or "",
                password=password or "",
                serial_port=serial_port or "",
                baudrate=baudrate or 9600,
                hostname=host or "抽象的工作台-Device",
                encoding=encoding or "",
            )
            dialect = get_dialect(vendor or "huawei")
            label = f"{protocol}://{host or serial_port}"

        await websocket.send_json({"type": "status", "data": f"正在连接 {label} …"})

        try:
            await loop.run_in_executor(io_pool, connector.connect, 12.0)
        except ConnectorError as e:
            await websocket.send_json({"type": "error", "data": str(e)})
            await websocket.close()
            return

        await websocket.send_json({
            "type": "connected",
            "data": label,
            "stream": bool(getattr(connector, "supports_stream", False)),
        })

        # 注册到活动会话中心：配置写入将复用本会话执行命令
        live = LiveSession(connector, device_id)
        hub_register(live)

        # 会话初始化：静默关闭分页 + 自动 enable（不再把初始化报错刷到终端）
        await loop.run_in_executor(io_pool, prepare_session, connector, dialect)

        examples = " / ".join((dialect.example_cmds or [])[:3])
        banner = (
            f"抽象的工作台 会话已建立 · {label}\r\n"
            f"厂商方言: {dialect.label} · 分页已关闭 · 特权模式已尝试进入\r\n"
            + (f"示例命令: {examples}\r\n" if examples else "")
            + "直接输入命令即达设备，输出实时回显；配置写入请走「配置写入」。\r\n"
        )
        await websocket.send_json({"type": "stream", "data": banner.replace("\n", "\r\n")})

        if getattr(connector, "supports_stream", False):
            # 真流式：设备输出随时推送，按键即时下发
            async def pump():
                try:
                    while True:
                        chunk = await loop.run_in_executor(io_pool, connector.read_available)
                        if chunk:
                            if live:
                                live.on_chunk(chunk)
                            await websocket.send_json({"type": "stream", "data": chunk})
                        else:
                            await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    pass
                except Exception:  # noqa: BLE001
                    pass

            pump_task = asyncio.create_task(pump())
            try:
                # 让设备回显一次提示符
                await loop.run_in_executor(io_pool, connector.write_raw, "\r\n")
                while True:
                    msg = await websocket.receive_json()
                    mtype = msg.get("type")
                    if mtype == "input":
                        line = msg.get("data", "")
                        await loop.run_in_executor(
                            io_pool, connector.write_raw, line + connector.line_ending
                        )
                    elif mtype == "key":
                        # 单个控制字符（如 Ctrl+C = \x03、Backspace = \x08）
                        await loop.run_in_executor(io_pool, connector.write_raw, msg.get("data", ""))
                    elif mtype == "encoding":
                        # 实时切换终端字符编码：只影响之后收到的字节如何解码
                        from services.encoding import normalize

                        connector.encoding = normalize(msg.get("data", ""))
                        await websocket.send_json({
                            "type": "encoding",
                            "data": connector.encoding,
                        })
                    elif mtype == "disconnect":
                        break
            finally:
                pump_task.cancel()
        else:
            # 模拟设备：命令→即时回显（无真实通道）
            while True:
                msg = await websocket.receive_json()
                mtype = msg.get("type")
                if mtype in ("input", "key"):
                    command = msg.get("data", "")
                    if mtype == "key" and command == "\x03":
                        await websocket.send_json({"type": "stream", "data": "^C\r\n"})
                        continue
                    try:
                        out = await loop.run_in_executor(io_pool, connector.run, command, 20.0)
                        # 模拟设备无真实回显；客户端已本地回显输入行，此处只回输出
                        echo = (out + "\r\n" if out else "")
                        if live:
                            live.on_chunk(echo)
                        await websocket.send_json({"type": "stream", "data": echo})
                    except Exception as e:  # noqa: BLE001
                        await websocket.send_json({"type": "error", "data": f"命令执行失败: {e}"})
                elif mtype == "encoding":
                    from services.encoding import normalize

                    connector.encoding = normalize(msg.get("data", ""))
                    await websocket.send_json({"type": "encoding", "data": connector.encoding})
                elif mtype == "disconnect":
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.exception("ws session error")
        try:
            await websocket.send_json({"type": "error", "data": f"会话异常: {e}"})
        except Exception:  # noqa: BLE001
            pass
    finally:
        hub_unregister(device_id)
        io_pool.shutdown(wait=False)
        db.close()
        if connector:
            try:
                connector.close()
            except Exception:  # noqa: BLE001
                pass
