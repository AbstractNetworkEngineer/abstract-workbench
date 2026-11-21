"""厂商方言驱动：决定"连上之后说什么话"。与传输层（SSH/Telnet/Serial）正交。"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class VendorDialect:
    name: str
    label: str
    config_cmd: str = "display current-configuration"
    version_cmd: str = "display version"
    save_cmd: str = "save"
    startup_cmd: str = "display startup"
    paging_cmds: List[str] = field(default_factory=lambda: ["screen-length 0 temporary"])
    enable_cmd: str = ""  # 进入特权模式的命令（Cisco/DCN 系需要 enable）
    view_enter: str = "system-view"
    view_exit: str = "quit"
    prompt_hint: str = "<hostname> / [hostname]"
    example_cmds: List[str] = field(default_factory=list)


DIALECTS = {
    "huawei": VendorDialect(
        name="huawei",
        label="华为 Huawei",
        config_cmd="display current-configuration",
        version_cmd="display version",
        save_cmd="save",
        paging_cmds=["screen-length 0 temporary"],
        prompt_hint="<Huawei> / [Huawei]",
        example_cmds=["display version", "display current-configuration", "display ip interface brief"],
    ),
    "h3c": VendorDialect(
        name="h3c",
        label="新华三 H3C",
        config_cmd="display current-configuration",
        version_cmd="display version",
        save_cmd="save force",
        paging_cmds=["screen-length 0 temporary"],
        prompt_hint="<H3C> / [H3C]",
        example_cmds=["display version", "display current-configuration", "display ip interface brief"],
    ),
    "dcn": VendorDialect(
        name="dcn",
        label="神州数码 DCN",
        config_cmd="show running-config",
        version_cmd="show version",
        save_cmd="write memory",
        paging_cmds=["terminal length 0"],
        enable_cmd="enable",
        view_enter="configure terminal",
        view_exit="exit",
        prompt_hint="DCN-Device> / DCN-Device#",
        example_cmds=["show version", "show running-config", "show ip interface brief", "show vlan"],
    ),
    "cisco": VendorDialect(
        name="cisco",
        label="思科 Cisco",
        config_cmd="show running-config",
        version_cmd="show version",
        save_cmd="write memory",
        paging_cmds=["terminal length 0"],
        enable_cmd="enable",
        view_enter="configure terminal",
        view_exit="exit",
        prompt_hint="Router> / Router#",
        example_cmds=["show version", "show running-config", "show ip interface brief"],
    ),
    "generic": VendorDialect(
        name="generic",
        label="通用（show 风格）",
        config_cmd="show running-config",
        version_cmd="show version",
        save_cmd="write",
        paging_cmds=["terminal length 0", "no paging"],
        enable_cmd="enable",
        view_enter="configure terminal",
        view_exit="exit",
        prompt_hint="device> / device#",
        example_cmds=["show version", "show running-config"],
    ),
}


def get_dialect(vendor: str) -> VendorDialect:
    return DIALECTS.get(vendor, DIALECTS["generic"])
