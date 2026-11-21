"""统一连接器抽象层：SSH / Telnet / Serial / 带外 / 模拟 设备共用同一接口。"""

import re
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
AUTH_PROMPT_RE = re.compile(r"(?i)(password|username|user name|login|passphrase)\s*:?\s*$")


class ConnectorError(Exception):
    pass


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def looks_like_prompt(data: str) -> bool:
    """判断缓冲区末尾是否是设备 CLI 提示符（如 <SW1> / [SW1] / SW1>）。"""
    d = strip_ansi(data).replace("\r", "").rstrip()
    if not d:
        return False
    last = d.splitlines()[-1].strip()
    if not (0 < len(last) < 120):
        return False
    return bool(re.search(r"[>\]]$", last)) or last.endswith("#")


class NetworkConnector(ABC):
    """所有连接方式的统一接口。"""

    supports_stream = False  # 是否支持字符级流式交互

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.password = kwargs.get("password", "") or ""
        self._decoder = None  # 必须先于 encoding 赋值（setter 会读它）
        self._connected = False
        # 终端字符编码：设备回显字节按它解码（国产设备常见 GBK/GB18030）
        self.encoding = kwargs.get("encoding", "") or ""

    def _get_decoder(self):
        from services.encoding import StreamDecoder, resolve

        if self._decoder is None:
            self._decoder = StreamDecoder(resolve(self.encoding))
        return self._decoder

    @property
    def encoding(self) -> str:
        return self._encoding

    @encoding.setter
    def encoding(self, value: str) -> None:
        """切编码 = 重建解码器，丢弃残缺字节缓存（只影响之后收到的数据）。"""
        self._encoding = value or ""
        if self._decoder is not None:
            from services.encoding import resolve

            self._decoder.set_encoding(resolve(self._encoding))

    @property
    def connected(self) -> bool:
        return self._connected

    def decode(self, raw: bytes | str) -> str:
        """把设备回显字节转成文本。

        走**增量解码器**：一次 recv 的字节边界随机，GBK 汉字会被切成两半，
        逐包独立解码会让整包中文变成 ▯▯▯（U+FFFD）。增量解码器把残缺尾巴
        缓存到下一次读取再解，和 SecureCRT 行为一致。
        """
        return self._get_decoder().decode(raw)

    def flush_decoder(self) -> str:
        """收尾：把缓存里残缺的字节按错误替换吐出来（会话结束时调用）。"""
        if self._decoder is None:
            return ""
        return self._decoder.decode(b"", final=True)

    def encode(self, text: str) -> bytes:
        """按本连接的字符编码把命令文本转成字节。未指定时用全局默认编码。"""
        from services.encoding import resolve, safe_encode

        return safe_encode(text, resolve(self.encoding))

    def read_available(self) -> str:
        """读取当前可得的原始输出（流式模式用），无数据返回空串。"""
        return ""

    def write_raw(self, data: str) -> None:
        """直接向设备写入原始字符（流式模式用）。"""
        raise ConnectorError("该连接方式不支持流式交互")

    @abstractmethod
    def connect(self, timeout: float = 12.0) -> None:
        ...

    @abstractmethod
    def run(self, command: str, timeout: float = 15.0) -> str:
        """发送一条命令并读取到下一个提示符为止的完整输出。"""
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()


class LineBasedConnector(NetworkConnector):
    """基于"发送命令→读到提示符"的连接器公共实现（SSH/Telnet/Serial 共用）。

    所有通道 IO 都经 _io_lock 串行化，防止多线程并发读写把字符顺序写乱。
    """

    prompt_stable_delay = 0.15
    line_ending = "\n"
    supports_stream = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._io_lock = threading.RLock()

    def read_available(self) -> str:
        with self._io_lock:
            return self._recv()

    def write_raw(self, data: str) -> None:
        with self._io_lock:
            self._send(data)

    def _stopped(self, data: str) -> bool:
        """提示符 或 认证/密码询问（如 Password:）都视为一次读取结束。"""
        if looks_like_prompt(data):
            return True
        d = strip_ansi(data).replace("\r", "").rstrip()
        if not d:
            return False
        return bool(AUTH_PROMPT_RE.search(d.splitlines()[-1].strip()))

    def _read_until_prompt(self, timeout: float = 15.0) -> str:
        end = time.time() + timeout
        data = ""
        while time.time() < end:
            chunk = self._recv()
            if chunk:
                data += chunk
                if self._stopped(data):
                    # 出现结束标记后再静默一小段时间，防止输出中途误判
                    settle_end = time.time() + self.prompt_stable_delay
                    while time.time() < settle_end:
                        extra = self._recv()
                        if extra:
                            data += extra
                            settle_end = time.time() + self.prompt_stable_delay
                    if self._stopped(data):
                        return data
            else:
                time.sleep(0.03)
        return data

    def _recv(self) -> str:  # pragma: no cover - 由子类实现
        raise NotImplementedError

    def run(self, command: str, timeout: float = 15.0) -> str:
        with self._io_lock:
            self._send(command + self.line_ending)
            raw = self._read_until_prompt(timeout)
            # 设备询问密码（enable 密码等）时自动应答
            d = strip_ansi(raw).replace("\r", "").rstrip()
            if d and AUTH_PROMPT_RE.search(d.splitlines()[-1].strip()) and self.password:
                self._send(self.password + self.line_ending)
                raw += self._read_until_prompt(timeout)
            return self._clean_output(raw, command)

    @staticmethod
    def _clean_output(raw: str, command: str) -> str:
        text = strip_ansi(raw).replace("\r", "")
        lines = text.split("\n")
        # 去掉命令回显的第一行
        if lines and command.strip() and command.strip() in lines[0]:
            lines = lines[1:]
        # 去掉末尾提示符行
        while lines and looks_like_prompt(lines[-1] + "\n"):
            lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def _send(self, data: str) -> None:  # pragma: no cover
        raise NotImplementedError
