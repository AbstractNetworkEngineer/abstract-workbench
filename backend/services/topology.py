"""拓扑发现：从 LLDP / CDP / ARP 推出设备邻居关系，供前端画拓扑图。

不依赖 SNMP，直接用 CLI 采集：
  - LLDP 邻居（华为/H3C `display lldp neighbor brief`，思科/DCN `show lldp neighbors`）
  - CDP 邻居（思科系 `show cdp neighbors detail`，作 LLDP 未启用时的补充）
  - ARP 表（把邻居名/接口映射到管理 IP）
  - 接口地址（确认自身管理 IP）

解析是格式宽容的：按列位置 + 已知列名切分，兼容各厂商缩写（GE0/0/1 / Gi0/1 / GigabitEthernet0/0/1）。
"""

import re

from connectors import ConnectorError, get_dialect
from services.executor import execute_on_device, serial_hint

# 接口名归一化：前缀映射（长名优先），不做单词边界匹配 —— Gi0/1 与 GE0/0/1 都要归到 GE
_IF_PREFIX = [
    ("gigabitethernet", "GE"), ("tengigabitethernet", "TE"),
    ("fortygigabitethernet", "FO"), ("hundredgigabitethernet", "HGE"),
    ("fastethernet", "FE"), ("ethernet", "Eth"),
    ("bridge-aggregation", "BAGG"), ("port-channel", "Po"),
    ("vlanif", "Vlanif"), ("loopback", "Loop"), ("null", "Nu"), ("tunnel", "Tun"),
    ("gig", "GE"), ("gi", "GE"), ("te", "TE"), ("fa", "FE"), ("fo", "FO"),
]


def _norm_if(name: str) -> str:
    s = (name or "").strip().replace(" ", "")
    if not s:
        return ""
    low = s.lower()
    for pref, rep in _IF_PREFIX:
        if low.startswith(pref):
            rest = s[len(pref):]
            # 去掉前缀与数字之间多余的分隔符：Gi/0/1 -> 0/1
            rest = rest.lstrip("/_-")
            return rep + rest
    return s


def _norm_dev(name: str) -> str:
    s = (name or "").strip()
    # 去掉 LLDP/CDP 常见后缀（序列号、括号域名）
    s = re.sub(r"\s*\(.*?\)\s*$", "", s)
    s = re.sub(r"\.+\S+$", "", s)  # 去掉域名后缀
    return s.strip()


def parse_lldp_brief(text: str) -> list[dict]:
    """华为/H3C：display lldp neighbor brief

    Local Intf   Neighbor Dev         Neighbor Intf    Expire Time
    GE0/0/1      SW-Core              GE0/0/24         94
    """
    rows = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or re.match(r"(?i)^(local\s*intf|total\s*items|---|\+\+)", s):
            continue
        parts = re.split(r"\s{2,}", s)
        if len(parts) >= 3 and re.match(r"(?i)^[a-z]{1,6}\d", parts[0]):
            rows.append({
                "local_if": _norm_if(parts[0]),
                "neighbor": _norm_dev(parts[1]),
                "remote_if": _norm_if(parts[2]),
                "proto": "lldp",
            })
    return rows


def parse_lldp_cisco(text: str) -> list[dict]:
    """思科/DCN：show lldp neighbors

    Device ID        Local Intf     Hold-time  Capability      Port ID
    SW-Core          Gi0/1          120        B               Gi0/24
    """
    rows = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or re.match(r"(?i)^(device\s*id|total\s*entries|---)", s):
            continue
        parts = re.split(r"\s{2,}", s)
        if len(parts) >= 2 and not re.match(r"(?i)^[a-z]{1,6}\d", parts[0]):
            # 第一列是设备名，第二列是本地接口
            rows.append({
                "local_if": _norm_if(parts[1]),
                "neighbor": _norm_dev(parts[0]),
                "remote_if": _norm_if(parts[-1]) if len(parts) >= 3 else "",
                "proto": "lldp",
            })
    return rows


def parse_cdp(text: str) -> list[dict]:
    """show cdp neighbors detail / show cdp neighbors"""
    rows = []
    # detail 格式：块状，取 Device ID / Interface / Port ID
    for block in re.split(r"(?m)^\s*$", text):
        dev = re.search(r"(?im)^\s*Device\s*ID\s*[:：]?\s*(\S+)", block)
        # Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet0/24
        loc = re.search(r"(?im)Interface\s*[:：]?\s*([^,]+?)\s*,\s*Port\s*ID", block)
        rem = re.search(r"(?i)Port\s*ID(?:\s*\(.*?\))?\s*[:：]\s*(\S+)", block)
        if dev and loc:
            rows.append({
                "local_if": _norm_if(loc.group(1)),
                "neighbor": _norm_dev(dev.group(1)),
                "remote_if": _norm_if(rem.group(1)) if rem else "",
                "proto": "cdp",
            })
    # 简表格式：Device ID / Local Intrfce / Holdtme / Capability / Platform / Port ID
    if not rows:
        for ln in text.splitlines():
            s = ln.strip()
            if not s or re.match(r"(?i)^(device\s*id|total\s*entries|---)", s):
                continue
            parts = re.split(r"\s{2,}", s)
            if len(parts) >= 2:
                rows.append({
                    "local_if": _norm_if(parts[1]),
                    "neighbor": _norm_dev(parts[0]),
                    "remote_if": _norm_if(parts[-1]),
                    "proto": "cdp",
                })
    return rows


def parse_arp(text: str) -> dict:
    """ARP 表：把 MAC → IP 存起来，用于给邻居补管理地址。"""
    mac2ip: dict[str, str] = {}
    ip2mac: dict[str, str] = {}
    for ln in text.splitlines():
        m = re.search(
            r"(\d{1,3}(?:\.\d{1,3}){3})\s+\d+\s+((?:[0-9a-f]{4}\.){2}[0-9a-f]{4}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2})",
            ln,
            re.I,
        )
        if m:
            ip, mac = m.group(1), m.group(2).lower()
            mac2ip[mac] = ip
            ip2mac[ip] = mac
    return {"mac2ip": mac2ip, "ip2mac": ip2mac}


def parse_self_ip(text: str) -> str:
    """从接口地址表里挑一个非环回的三层地址作为自身管理 IP。"""
    cands = re.findall(r"(?m)^\s*(\S+)\s+(\d{1,3}(?:\.\d{1,3}){3})\s+", text)
    for name, ip in cands:
        if not ip.startswith("127.") and _norm_if(name).lower().startswith("vlanif") is False:
            if not re.match(r"(?i)^(loop|nu|null|tunnel)", name):
                return ip
    for name, ip in cands:
        if not ip.startswith("127."):
            return ip
    return ""


def collect_topology(device) -> dict:
    """采集并解析邻居，返回 nodes/links 结构。"""
    d = get_dialect(device.vendor)
    huawei_like = d.name in ("huawei", "h3c")

    cmds = [
        "display lldp neighbor brief" if huawei_like else "show lldp neighbors",
        "show cdp neighbors detail" if not huawei_like else "display lldp neighbor verbose",
        "show arp" if not huawei_like else "display arp",
        "show ip interface brief" if not huawei_like else "display ip interface brief",
    ]

    try:
        results, via = execute_on_device(device, cmds, timeout_each=20.0)
    except ConnectorError as e:
        raise ConnectorError(f"连接设备失败：{e}{serial_hint(device)}") from e

    out = {r["command"]: (r.get("output") or "") for r in results}

    neigh: list[dict] = []
    neigh.extend(parse_lldp_brief(out[cmds[0]]))
    if not neigh:
        neigh.extend(parse_lldp_cisco(out[cmds[0]]))
    neigh.extend(parse_cdp(out[cmds[1]]))

    arp = parse_arp(out[cmds[2]])
    self_ip = parse_self_ip(out[cmds[3]])

    # 同一对 (local_if, neighbor) 只留一条
    seen = set()
    links = []
    for n in neigh:
        if not n["local_if"] or not n["neighbor"]:
            continue
        key = (n["local_if"].lower(), n["neighbor"].lower())
        if key in seen:
            continue
        seen.add(key)
        links.append(n)

    # 建节点
    nodes = [{"id": "__self__", "label": device.name, "kind": "self", "ip": self_ip, "vendor": device.vendor}]
    idx: dict[str, str] = {}
    for l in links:
        nid = l["neighbor"]
        if nid not in idx:
            idx[nid] = nid
            nodes.append({"id": nid, "label": nid, "kind": "neighbor", "ip": "", "vendor": ""})

    warnings = []
    if not links:
        warnings.append("未发现 LLDP/CDP 邻居。请确认设备已启用 lldp enable / cdp run，且链路对端也支持邻居发现。")
    if not self_ip:
        warnings.append("未采集到自身管理 IP，拓扑节点可能缺少地址标注。")
    unsupported = [r["command"] for r in results if not r.get("ok")]
    if unsupported:
        warnings.append("部分采集命令不被支持：" + "、".join(unsupported[:3]))

    return {
        "device": {"id": device.id, "name": device.name, "vendor": d.label},
        "self": nodes[0],
        "nodes": nodes,
        "links": [
            {
                "from": "__self__",
                "to": l["neighbor"],
                "local_if": l["local_if"],
                "remote_if": l["remote_if"],
                "proto": l["proto"],
            }
            for l in links
        ],
        "arp_count": len(arp["mac2ip"]),
        "via": via,
        "warnings": warnings,
    }
