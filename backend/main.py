"""抽象的工作台 — 网络设备统一运维工作台（后端入口）"""

import asyncio
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

import ws_terminal
from database import init_db
from routers import ai, audits, backups, capture, changes, detect, devices, drift, inspect, manuals, settings, stats, strategies, topology
from scheduler import scheduler_loop
from services.security import get_token, origin_ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

_scheduler_task: asyncio.Task | None = None

HTTP_PORT = int(os.environ.get("ABSTRACT_WORKBENCH_PORT", "18765"))


def find_dist() -> Path | None:
    """定位前端构建产物（开发目录 或 PyInstaller 打包目录）。"""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys._MEIPASS) / "webdist")
    candidates.append(Path(__file__).resolve().parent.parent / "frontend" / "dist")
    for c in candidates:
        if (c / "index.html").exists():
            return c
    return None


DIST_DIR = find_dist()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task
    init_db()
    get_token()  # 首次启动生成访问令牌
    # 载入终端字符编码默认值（设备未指定编码时用它）
    try:
        from database import SessionLocal
        from services.ai import get_settings
        from services.encoding import set_default

        db = SessionLocal()
        try:
            set_default(get_settings(db).get("term_encoding", "utf-8"))
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass
    _scheduler_task = asyncio.create_task(scheduler_loop())
    yield
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="抽象的工作台",
    description="网络设备统一运维工作台 —— SSH/Telnet/Serial/带外通用连接 + AI 副驾驶",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)


# ---------------- 安全中间件 ----------------
TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{20,}$")


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path

    # 静态资源与健康检查放行；/api 与 /ws 需要过安全闸
    is_data_path = path.startswith("/api/") or path.startswith("/ws")
    is_bootstrap = not is_data_path or path == "/api/health"

    if is_data_path and not is_bootstrap:
        origin = request.headers.get("origin")
        if origin is not None:
            # 浏览器请求：必须同源（拦截恶意网页驱动本机 API）
            if not origin_ok(origin, HTTP_PORT):
                return JSONResponse({"detail": "跨域请求被拒绝"}, status_code=403)
        else:
            # 无 Origin 的脚本/命令行请求：必须携带访问令牌
            token = request.headers.get("x-access-token") or request.query_params.get("token")
            if not token or not TOKEN_RE.match(token) or token != get_token():
                return JSONResponse({"detail": "未授权：缺少或无效的访问令牌"}, status_code=401)

    response = await call_next(request)
    # 安全响应头
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------- 业务路由 ----------------
app.include_router(devices.router)
app.include_router(backups.router)
app.include_router(strategies.router)
app.include_router(audits.router)
app.include_router(ai.router)
app.include_router(changes.router)
app.include_router(settings.router)
app.include_router(stats.router)
app.include_router(manuals.router)
app.include_router(inspect.router)
app.include_router(drift.router)
app.include_router(detect.router)
app.include_router(topology.router)
app.include_router(capture.router)
app.include_router(ws_terminal.router)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "抽象的工作台"}


@app.get("/{full_path:path}")
def spa(full_path: str):
    """静态资源托管 + 前端路由兜底；把访问令牌注入 index.html。"""
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        raise HTTPException(404, "not found")
    if DIST_DIR is None:
        return {"ok": True, "hint": "前端未构建，请先执行 cd frontend && npm run build"}
    target = DIST_DIR / full_path
    if full_path and target.is_file():
        return FileResponse(target)
    html = (DIST_DIR / "index.html").read_text(encoding="utf-8")
    token = get_token()
    html = html.replace("__NETDECK_TOKEN__", token)
    from fastapi.responses import HTMLResponse

    return HTMLResponse(html)
