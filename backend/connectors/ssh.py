"""SSH 连接器（Paramiko），兼容部分老旧设备的算法套件。"""

import socket
import time

import paramiko

from .base import ConnectorError, LineBasedConnector


class SshConnector(LineBasedConnector):
    def __init__(self, host, port=22, username="", password="", **kw):
        super().__init__(password=password, **kw)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client: paramiko.SSHClient | None = None
        self.shell = None

    def connect(self, timeout: float = 12.0) -> None:
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            # 老设备常只支持旧算法，这里放开常见 legacy 套件
            sock = socket.create_connection((self.host, self.port), timeout=timeout)
            transport = paramiko.Transport(sock)
            transport.local_cipher_list = "aes128-cbc,aes256-cbc,3des-cbc"
            transport.remote_cipher_list = "aes128-cbc,aes256-cbc,3des-cbc"
            transport.connect(
                username=self.username or None,
                password=self.password or None,
                timeout=timeout,
            )
            self.client._transport = transport
            self.shell = self.client.invoke_shell(width=200, height=50)
            self.shell.settimeout(0.4)
        except Exception as e:
            self.close()
            raise ConnectorError(f"SSH 连接失败 {self.host}:{self.port} - {e}") from e
        # 等待登录后的首个提示符
        banner = self._read_until_prompt(timeout=timeout)
        if not banner:
            self.close()
            raise ConnectorError("SSH 已连接但未读到设备提示符")
        self._connected = True

    def _recv(self) -> str:
        try:
            if self.shell.recv_ready():
                data = self.shell.recv(4096)
                return self.decode(data)
        except (socket.timeout, OSError):
            return ""
        return ""

    def _send(self, data: str) -> None:
        if not self.shell:
            raise ConnectorError("SSH 会话未连接")
        self.shell.sendall(self.encode(data))

    def close(self) -> None:
        self._connected = False
        try:
            if self.shell:
                self.shell.close()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.shell = None
        self.client = None
