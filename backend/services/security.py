"""安全模块：访问令牌、跨域防护、凭据加密。

威胁模型：
1. 恶意网页驱动本机 API（浏览器打 127.0.0.1）→ Origin 校验 + 访问令牌双闸
2. 局域网直连盗用 → 默认只监听回环；令牌校验无 Origin 的直连请求
3. 数据库泄露 → 设备密码 Fernet 加密落盘（密钥在 data/.secret_key）
"""

import os
import secrets
from pathlib import Path

from database import DATA_DIR

TOKEN_FILE = DATA_DIR / ".secret_token"
KEY_FILE = DATA_DIR / ".secret_key"
_TOKEN: str | None = None
_FERNET = None


def get_token() -> str:
    """首次启动生成随机访问令牌并持久化。"""
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    if TOKEN_FILE.exists():
        _TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not _TOKEN:
        _TOKEN = secrets.token_urlsafe(32)
        TOKEN_FILE.write_text(_TOKEN, encoding="utf-8")
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass
    return _TOKEN


def _get_fernet():
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    if KEY_FILE.exists():
        key = KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except OSError:
            pass
    _FERNET = Fernet(key)
    return _FERNET


def encrypt_str(plain: str) -> str:
    """加密敏感字段；cryptography 不可用时退化为明文（带标记）。"""
    if not plain:
        return ""
    f = _get_fernet()
    if f is None:
        return "plain:" + plain
    return "enc:" + f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_str(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith("plain:"):
        return stored[len("plain:"):]
    if stored.startswith("enc:"):
        f = _get_fernet()
        if f is None:
            return ""
        try:
            return f.decrypt(stored[len("enc:"):].encode("ascii")).decode("utf-8")
        except Exception:  # noqa: BLE001
            return ""
    # 兼容历史明文
    return stored


def allowed_origins(http_port: int) -> set[str]:
    """允许的浏览器来源（同源 + 开发服务器）。"""
    origins = {
        f"http://127.0.0.1:{http_port}",
        f"http://localhost:{http_port}",
        f"http://[::1]:{http_port}",
    }
    dev = os.environ.get("ABSTRACT_WORKBENCH_DEV_ORIGINS", "")
    if dev:
        origins.update(x.strip() for x in dev.split(",") if x.strip())
    return origins


def origin_ok(origin: str | None, http_port: int) -> bool:
    """浏览器请求必须同源；无 Origin（脚本/命令行）必须携带令牌。"""
    if not origin:
        return False
    return origin.rstrip("/") in allowed_origins(http_port)
