"""Serial（Console 口）连接器 —— 设备无 IP / 变砖时的最后通道。

程序必须运行在物理连接着 Console 线的机器上。
"""

import time

from .base import ConnectorError, LineBasedConnector


class SerialConnector(LineBasedConnector):
    line_ending = "\r"  # Cisco/DCN 风格 Console 口约定回车符

    def __init__(self, serial_port="", baudrate=9600, **kw):
        super().__init__(**kw)
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.ser = None

    def connect(self, timeout: float = 12.0) -> None:
        try:
            import serial  # pyserial
        except ImportError as e:
            raise ConnectorError("未安装 pyserial，无法使用串口连接") from e
        if not self.serial_port:
            raise ConnectorError("未指定串口（如 COM3 / /dev/ttyUSB0）")
        try:
            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=self.baudrate,
                timeout=0.4,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
        except Exception as e:
            raise ConnectorError(f"打开串口失败 {self.serial_port} - {e}") from e

        # 串口常需敲回车才出提示符
        self.ser.write(b"\r\n")
        time.sleep(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\n")
        tail = self._read_until_prompt(timeout=timeout)
        if not tail:
            self.close()
            raise ConnectorError("串口已打开但未读到设备提示符（检查波特率/接线）")
        self._connected = True

    def _recv(self) -> str:
        if not self.ser or not self.ser.is_open:
            return ""
        try:
            n = self.ser.in_waiting
            if n:
                return self.decode(self.ser.read(n))
        except Exception:
            return ""
        return ""

    def _send(self, data: str) -> None:
        if not self.ser:
            raise ConnectorError("串口会话未打开")
        self.ser.write(self.encode(data))
        self.ser.flush()

    def close(self) -> None:
        self._connected = False
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
