"""连接器工厂：根据设备记录（或临时连接参数）创建对应连接器。"""

from .base import ConnectorError, NetworkConnector
from .mock import MockConnector
from .serial_conn import SerialConnector
from .ssh import SshConnector
from .telnet import TelnetConnector


def create_connector(
    protocol: str,
    host: str = "",
    port: int = 22,
    username: str = "",
    password: str = "",
    serial_port: str = "",
    baudrate: int = 9600,
    hostname: str = "抽象的工作台-SW1",
    encoding: str = "",
) -> NetworkConnector:
    """encoding 为设备回显的字符编码（空则用全局默认，见 services.encoding）。"""
    protocol = (protocol or "ssh").lower()
    enc = encoding or ""
    if protocol == "ssh":
        if not host:
            raise ConnectorError("SSH 需要填写设备 IP/主机名")
        return SshConnector(host=host, port=port or 22, username=username, password=password, encoding=enc)
    if protocol == "telnet":
        if not host:
            raise ConnectorError("Telnet 需要填写设备 IP/主机名")
        return TelnetConnector(host=host, port=port or 23, username=username, password=password, encoding=enc)
    if protocol == "serial":
        return SerialConnector(serial_port=serial_port, baudrate=baudrate or 9600, password=password, encoding=enc)
    if protocol in ("mock", "demo"):
        return MockConnector(hostname=hostname or "抽象的工作台-SW1", encoding=enc)
    if protocol in ("outband", "oob", "redfish"):
        # 带外管理一期：通过管理口仍走 SSH/Telnet，字段复用 host/port
        if not host:
            raise ConnectorError("带外管理口需要填写管理 IP")
        return SshConnector(host=host, port=port or 22, username=username, password=password, encoding=enc)
    raise ConnectorError(f"不支持的连接方式: {protocol}")


def connector_from_device(device) -> NetworkConnector:
    from services.security import decrypt_str

    return create_connector(
        protocol=device.protocol,
        host=device.host,
        port=device.port,
        username=device.username,
        password=decrypt_str(device.password or ""),
        serial_port=device.serial_port,
        baudrate=device.baudrate,
        hostname=device.name or "抽象的工作台-Device",
        encoding=getattr(device, "encoding", "") or "",
    )
