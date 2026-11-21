"""Telnet 连接器（老设备开局常用），最小 IAC 协商实现。"""

import socket
import time

from .base import ConnectorError, LineBasedConnector, strip_ansi

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240


class TelnetConnector(LineBasedConnector):
    line_ending = "\r\n"

    def __init__(self, host, port=23, username="", password="", **kw):
        super().__init__(password=password, **kw)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sock: socket.socket | None = None
        self._buf = b""

    def connect(self, timeout: float = 12.0) -> None:
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
            self.sock.settimeout(0.4)
        except OSError as e:
            raise ConnectorError(f"Telnet 连接失败 {self.host}:{self.port} - {e}") from e

        # 登录交互：等 Username/Password 提示
        deadline = time.time() + timeout
        acc = ""
        stage = "banner"
        while time.time() < deadline:
            acc += self._recv()
            low = strip_ansi(acc).lower()
            if stage == "banner" and ("username" in low or "login" in low or "user name" in low):
                self._send(self.username + "\r\n")
                stage = "password"
                acc = ""
            elif stage == "password" and "password" in low:
                self._send(self.password + "\r\n")
                stage = "done"
                acc = ""
                break
            elif "username" not in low and ("#" in low or ">" in low or "]$" in low or "]" in low):
                # 已经直接给出提示符（免认证或已缓存会话）
                stage = "done"
                break
            else:
                time.sleep(0.05)

        tail = self._read_until_prompt(timeout=timeout)
        if stage != "done" and not tail and not acc:
            self.close()
            raise ConnectorError("Telnet 登录失败：未收到认证提示或设备提示符")
        self._connected = True

    def _recv(self) -> str:
        if not self.sock:
            return ""
        try:
            chunk = self.sock.recv(4096)
        except (socket.timeout, OSError):
            return ""
        if not chunk:
            return ""
        # 处理 IAC 协商：拒绝所有选项（回复 WONT/DONT）
        out = bytearray()
        i = 0
        while i < len(chunk):
            b = chunk[i]
            if b == IAC and i + 1 < len(chunk):
                cmd = chunk[i + 1]
                if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(chunk):
                    opt = chunk[i + 2]
                    if cmd == DO:
                        reply = bytes([IAC, WONT, opt])
                    elif cmd == WILL:
                        reply = bytes([IAC, DONT, opt])
                    else:
                        reply = b""
                    if reply and self.sock:
                        try:
                            self.sock.sendall(reply)
                        except OSError:
                            pass
                    i += 3
                    continue
                elif cmd == SB:
                    j = chunk.find(bytes([IAC, SE]), i)
                    i = (j + 2) if j != -1 else len(chunk)
                    continue
                else:
                    i += 2
                    continue
            out.append(b)
            i += 1
        return self.decode(bytes(out))

    def _send(self, data: str) -> None:
        if not self.sock:
            raise ConnectorError("Telnet 会话未连接")
        self.sock.sendall(self.encode(data))

    def close(self) -> None:
        self._connected = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
