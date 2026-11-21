"""模拟设备连接器 —— 无真实设备时完整演示工作台/备份/AI 流程。

模拟一台类华为/H3C 命令行风格的交换机。
"""

import time

from .base import ConnectorError, NetworkConnector

MOCK_CONFIG = """#
sysname NetDeck-SW1
#
vlan batch 1 10 100 200
#
dhcp enable
#
interface Vlanif1
 ip address 192.168.1.1 255.255.255.0
#
interface GigabitEthernet0/0/1
 port link-type trunk
 port trunk allow-pass vlan 10 100 200
#
interface GigabitEthernet0/0/2
 port link-type access
 port default vlan 10
#
interface GigabitEthernet0/0/24
 port link-type access
 port default vlan 1
#
stp enable
#
aaa
 authentication-scheme default
 authorization-scheme default
 accounting-scheme default
 local-user admin password cipher Admin@123
 local-user admin service-type terminal
#
return
"""

MOCK_VERSION = """Huawei Versatile Routing Platform Software
VRP (R) software, Version 5.170 (V200R003C00)
HUAWEI S5720-28P-LI-AC uptime is 128 days, 3 hours, 16 minutes
MPU version information
SDRAM : 1024 Mbytes
Flash : 512 Mbytes
"""

MOCK_BRIEF = """Interface                   IP Address      Physical   Protocol
Vlanif1                    192.168.1.1     up         up
GigabitEthernet0/0/1       unassigned      up         up
GigabitEthernet0/0/2       unassigned      up         up
GigabitEthernet0/0/24      unassigned      down       down
"""


class MockConnector(NetworkConnector):
    """类华为/H3C 交互模拟器。"""

    def __init__(self, hostname: str = "NetDeck-SW1", **kw):
        super().__init__(**kw)
        self.hostname = hostname
        self.in_system_view = False
        self._pending_save = False

    @property
    def prompt(self) -> str:
        if self.in_system_view:
            return f"[{self.hostname}]"
        return f"<{self.hostname}>"

    def connect(self, timeout: float = 12.0) -> None:
        time.sleep(0.1)
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def run(self, command: str, timeout: float = 15.0) -> str:
        if not self._connected:
            raise ConnectorError("模拟设备未连接")
        cmd = command.strip()
        low = cmd.lower()

        # 分页控制类命令
        if low in (
            "screen-length 0 temporary",
            "screen-length 0",
            "terminal length 0",
            "no paging",
            "undo screen-length",
        ):
            return ""

        if self._pending_save:
            self._pending_save = False
            if low in ("y", "yes"):
                return f"Info: The configuration file {self.hostname}.cfg has been saved."
            return "Info: Save cancelled."

        # 模式切换
        if low in ("system-view", "sys", "system", "enable", "ena", "configure terminal", "conf t"):
            self.in_system_view = True
            return ""
        if low in ("quit", "exit", "return"):
            if self.in_system_view:
                self.in_system_view = False
                return ""
            return ""

        if low in ("display current-configuration", "display current-configuration | include-regex .",
                   "show running-config", "show run"):
            return MOCK_CONFIG
        if low in ("display version", "show version"):
            return MOCK_VERSION
        if low in ("display ip interface brief", "show ip interface brief", "display ip int bri"):
            return MOCK_BRIEF
        if low.startswith("display vlan") or low == "show vlan":
            return ("VLAN ID: 1\nVLAN ID: 10\nVLAN ID: 100\nVLAN ID: 200")
        if low == "save" or low.startswith("save "):
            self._pending_save = True
            return "System will save the configuration. Continue? [Y/N]:"
        if low.startswith("ping"):
            target = cmd.split()[-1] if len(cmd.split()) > 1 else "192.168.1.1"
            return (
                f"PING {target}: 56 data bytes\n"
                f"  Request timeout.\n"
                f"  Reply from {target}: bytes=56 Sequence=1 ttl=255 time=3 ms\n"
                f"  Reply from {target}: bytes=56 Sequence=2 ttl=255 time=2 ms\n"
                f"\n  --- {target} ping statistics ---\n"
                f"    5 packets transmitted, 4 packets received,  20.00% packet loss\n"
                f"    round-trip min/avg/max = 2/2/3 ms"
            )
        if low.startswith("interface "):
            if not self.in_system_view:
                return "Error: Please enter system view first."
            return ""
        if low.startswith("vlan ") or low.startswith("vlan batch"):
            if not self.in_system_view:
                return "Error: Please enter system view first."
            return ""
        if low in ("display current-configuration",):
            return MOCK_CONFIG
        if low.startswith("display device") or low == "display device":
            return "NAME          STATUS  SOFTWARE VERSION\nS5720-28P     Normal  V200R003C00"
        if low.startswith("display interface") or low in ("show interfaces", "show interface"):
            return ("GigabitEthernet0/0/1 current state : UP\n"
                    "GigabitEthernet0/0/1 current mode : full-duplex, 1000Mb/s\n"
                    "Input: 120433 packets, 98231123 bytes, 12 errors\n"
                    "Output: 98122 packets, 72811922 bytes, 0 errors, 3 drops\n"
                    "GigabitEthernet0/0/2 current state : UP\n"
                    "Input: 51002 packets, 41001122 bytes, 0 errors\n"
                    "Output: 44211 packets, 33102211 bytes, 0 errors")
        if low in ("show ip route", "display ip routing-table"):
            return ("Codes: C - connected, S - static, R - RIP, O - OSPF\n"
                    "C 172.16.10.0/24 is directly connected, Vlan10\n"
                    "C 172.16.30.0/26 is directly connected, Vlan30\n"
                    "C 172.16.40.0/24 is directly connected, Vlan40\n"
                    "C 172.16.100.0/24 is directly connected, Vlan52\n"
                    "C 192.168.100.0/24 is directly connected, Vlan100\n"
                    "R 10.0.0.0/24 [120/1] via 172.16.30.2, Vlan30\n"
                    "R 218.5.18.0/27 [120/1] via 172.16.30.2, Vlan30\n"
                    "S 0.0.0.0/0 [1/0] via 218.5.18.1\n"
                    "Total routes are : 8 item(s)")
        if low in ("show mac-address-table", "display mac-address"):
            return ("MAC Address Table\n"
                    "Vlan    MAC Address       Type        Port\n"
                    "10      00e0.fc12.3456    Dynamic     Ethernet1/0/2\n"
                    "10      00e0.fc65.4321    Dynamic     Ethernet1/0/3\n"
                    "20      00e0.fc99.8877    Dynamic     Ethernet1/0/5\n"
                    "100     00e0.fcaa.bbcc    Static      Ethernet1/0/1")
        if low in ("show arp", "display arp"):
            return ("Address         Age (min)   Hardware Addr    Interface\n"
                    "172.16.10.2     5           00e0.fc12.3456   Vlan10\n"
                    "172.16.30.2     12          00e0.fc65.4321   Vlan30\n"
                    "192.168.100.2   3           00e0.fc99.8877   Vlan100")
        if low in ("show spanning-tree summary", "display stp brief", "show spanning-tree"):
            return ("Spanning-tree mode: MSTP\n"
                    "Root ID    Priority    32768\n"
                    "           Address     00e0.fcaa.bbcc\n"
                    "           This bridge is the root\n"
                    "Hello Time 2 sec  Max Age 20 sec  Forward Delay 15 sec\n"
                    "Instance 2 Vlan 20,200 : forwarding Ethernet1/0/3 Port-Channel1")
        if low in ("show ip ospf neighbor", "display ospf peer brief"):
            return ("OSPF Process 1 with Router ID 172.16.30.1\n"
                    "  Neighbor 172.16.30.2, area 0.0.0.0, Full\n"
                    "  Neighbor 10.0.0.1, area 0.0.0.0, Full")
        if low in ("show ip rip", "display rip"):
            return ("RIP process 1\n"
                    "  Network: 172.16.0.0\n"
                    "  Network: 192.168.100.0\n"
                    "  Summary: 2 networks, metric 1")
        if low in ("show ip dhcp binding", "display ip pool"):
            return ("IP address       Client-ID/Lease        Type\n"
                    "192.168.100.50   00e0.fc12.3456          Dynamic\n"
                    "192.168.100.51   00e0.fc65.4321          Dynamic")
        if low in ("show processes cpu", "display cpu-usage"):
            return ("CPU utilization for five seconds: 12%; one minute: 15%; five minutes: 18%\n"
                    "Memory utilization: 43%")
        if low in ("show logging", "display logbuffer"):
            return ("Syslog: 1280 messages\n"
                    "%LINK-3-UPDOWN: Interface Vlan20, changed state to up\n"
                    "%LINEPROTO-5-UPDOWN: Line protocol on Vlan20, changed state to up\n"
                    "No errors detected.")
        if low.startswith("undo ") or low.startswith("set "):
            if not self.in_system_view:
                return "Error: Please enter system view first."
            return ""
        if not cmd:
            return ""

        # 未知命令
        if self.in_system_view:
            return f"Error: Wrong parameter found at '^' position."
        return f"% Unrecognized command found at '^' position."


def mock_response(command: str, in_system_view: bool) -> tuple[str, bool]:
    """供测试使用的纯函数式模拟（无状态副本）。"""
    m = MockConnector()
    m.in_system_view = in_system_view
    m._connected = True
    out = m.run(command)
    return out, m.in_system_view
