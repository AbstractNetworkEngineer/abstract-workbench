"""包级运行状态发现：把抓包统计转成运维看得懂的结论。

这是 Wireshark 能力**真正融入巡检/检测**的入口 —— 不是跳到抓包页，
而是把广播风暴、ARP 泛洪、明文协议、重传这类问题直接判出来。
"""

import re

from services import capture as cap


def _num(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def packet_findings(path: str) -> dict:
    """分析抓包文件，产出 {total, findings, top_protocols, endpoints}。

    findings: [{level, cat, title, detail, evidence, deduct, fix}]
    """
    ana = cap.analyze_pcap(path)
    protos = ana.get("protocols", [])
    convs = ana.get("conversations", [])
    ends = ana.get("endpoints", [])
    expert = ana.get("expert", [])
    total = max(1, _num(ana.get("file", {}).get("packets")))

    # 取顶层协议帧数（depth=0）
    top = {r["proto"].lower(): _num(r["frames"]) for r in protos if r.get("depth", 0) == 0}
    allp = {r["proto"].lower(): _num(r["frames"]) for r in protos}
    pcts = {k: v / total for k, v in allp.items()}

    findings = []

    # 广播/组播风暴
    bcast = allp.get("arp", 0) + allp.get("lldp", 0) + allp.get("cdp", 0) + allp.get("stp", 0)
    igmp_mcast = allp.get("igmp", 0) + allp.get("mld", 0) + allp.get("ospf", 0)
    if total >= 20 and bcast / total > 0.25:
        findings.append({
            "level": "高", "cat": "稳定", "deduct": 12,
            "title": "广播/邻居通告流量偏高",
            "detail": f"二层广播类（ARP/LLDP/CDP/STP）占 {bcast / total:.0%}（{bcast}/{total} 帧），二层域存在环路或扫描行为的可能。",
            "evidence": [f"{k}={v} 帧" for k, v in allp.items() if k in ("arp", "lldp", "cdp", "stp")][:6],
            "fix": ["stp enable", "loopback-detection enable", "display stp brief"],
        })
    elif total >= 20 and igmp_mcast / total > 0.20:
        findings.append({
            "level": "中", "cat": "稳定", "deduct": 6,
            "title": "组播/路由协议流量偏高",
            "detail": f"IGMP/MLD/OSPF 类占 {igmp_mcast / total:.0%}，组播复制或邻居震荡。",
            "evidence": [f"{k}={v} 帧" for k, v in allp.items() if k in ("igmp", "mld", "ospf")][:6],
            "fix": ["display igmp-snooping", "display multicast routing-table"],
        })

    # ARP 泛洪
    arp_n = allp.get("arp", 0)
    if arp_n >= 100 and arp_n / total > 0.10:
        findings.append({
            "level": "高", "cat": "安全", "deduct": 12,
            "title": "ARP 泛洪",
            "detail": f"ARP 帧 {arp_n} 个（占 {arp_n / total:.0%}），疑似 ARP 扫描/欺骗或免费 ARP 异常。",
            "evidence": [f"arp={arp_n} / total={total}"],
            "fix": ["dhcp snooping enable", "arp anti-attack check user-bind enable"],
        })

    # 明文协议
    plain = [("telnet", 15), ("ftp", 10), ("http", 6), ("snmp", 8), ("tftp", 8), ("pop", 6), ("imap", 6)]
    for proto, ded in plain:
        n = allp.get(proto, 0)
        if n > 0:
            findings.append({
                "level": "中" if proto in ("telnet", "ftp", "tftp") else "低",
                "cat": "安全", "deduct": ded,
                "title": f"存在明文协议 {proto.upper()}",
                "detail": f"抓到 {n} 个 {proto.upper()} 帧，链路上可被嗅探账号口令/数据。",
                "evidence": [f"{proto}={n} 帧"],
                "fix": ["stelnet server enable", "undo telnet server enable"],
            })

    # 专家信息异常
    errs = sum(_num(e.get("count")) for e in expert if re.search(r"(?i)error", str(e.get("level", ""))))
    warns = sum(_num(e.get("count")) for e in expert if re.search(r"(?i)warn", str(e.get("level", ""))))
    if errs > 0:
        findings.append({
            "level": "高", "cat": "稳定", "deduct": 8,
            "title": "抓包内含协议异常",
            "detail": f"Wireshark 专家信息报出 {errs} 处 Error，可能存在校验和错误、畸形包、重传。",
            "evidence": [f"{e.get('level')}={e.get('count')}" for e in expert[:6]],
            "fix": ["display interface", "display cpu-usage"],
        })
    elif warns > 20:
        findings.append({
            "level": "低", "cat": "稳定", "deduct": 4,
            "title": "协议告警偏多",
            "detail": f"专家信息报出 {warns} 处 Warning（重传/乱序等），链路质量需关注。",
            "evidence": [f"{e.get('level')}={e.get('count')}" for e in expert[:6]],
            "fix": ["display interface", "display tcp statistics"],
        })

    # 单点流量集中
    if ends:
        top_end = ends[0]
        if total > 50 and _num(top_end.get("frames")) / (2 * total) > 0.55:
            findings.append({
                "level": "中", "cat": "容量", "deduct": 6,
                "title": "单点流量集中",
                "detail": f"地址 {top_end.get('address')} 收发 {_num(top_end.get('frames'))} 帧，占端点总量比例过高。",
                "evidence": [f"{top_end.get('address')} frames={top_end.get('frames')}"],
                "fix": ["display interface brief", "display traffic-policy"],
            })

    order = {"高": 0, "中": 1, "低": 2}
    findings.sort(key=lambda f: (order.get(f["level"], 9), -f["deduct"]))

    return {
        "file": ana.get("file", {}),
        "total": total,
        "findings": findings,
        "top_protocols": sorted(
            ({"proto": k, "frames": v, "pct": round(v / total, 4)} for k, v in allp.items()),
            key=lambda r: -r["frames"],
        )[:8],
        "top_endpoints": ends[:5],
        "expert_summary": expert[:6],
    }
