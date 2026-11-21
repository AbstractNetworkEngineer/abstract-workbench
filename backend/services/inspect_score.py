"""巡检确定性评分引擎：按固定规则扣分，同一份配置必出同一个分。

之前把打分交给 AI 自由发挥（temperature=0.2），同一台设备两次巡检分不一样，
看着就"不智能"。这里改成规则引擎：每条检查项有固定的类别与扣分，
分数由配置内容唯一决定；AI 只负责写分析叙述，不碰分数。
"""

import re

# (id, 类别, 严重度, 扣分, 标题, 说明模板, 修复命令)
# 类别：安全 / 规范 / 容量 / 稳定 ；严重度：高 / 中 / 低
RULES = [
    {
        "id": "plain_password",
        "cat": "安全", "level": "高", "deduct": 18,
        "title": "明文/弱口令",
        "pat": r"(?im)^\s*username\s+\S+.*\bpassword\s+0\s+\S+",
        "detail": "最高权限账户以明文存储口令（password 0），配置泄露即全线失守。",
        "fix": ["service password-encryption"],
    },
    {
        "id": "no_pw_encrypt",
        "cat": "安全", "level": "高", "deduct": 12,
        "title": "口令加密被关闭",
        "pat": r"(?im)^\s*no\s+service\s+password-encryption",
        "detail": "password-encryption 被显式关闭，后续所有口令将以明文保存在配置里。",
        "fix": ["service password-encryption"],
    },
    {
        "id": "no_login",
        "cat": "安全", "level": "高", "deduct": 12,
        "title": "认证失效",
        "pat": r"(?im)^\s*(?:line\s+(?:con|vty|aux).*\n(?:.*\n){0,6}?)?\s*no\s+login\b",
        "detail": "登录不需要任何认证，console/VTY 无门槛。",
        "fix": ["line vty 0 4", " login local", " transport input ssh"],
    },
    {
        "id": "telnet_plain",
        "cat": "安全", "level": "中", "deduct": 8,
        "title": "明文远程协议",
        "pat": r"(?im)^\s*(?:transport\s+input\s+.*telnet|telnet\s+server\s+enable)",
        "detail": "启用 Telnet 明文传输，账号口令可被链路窃听。",
        "fix": ["undo telnet server enable", "stelnet server enable"],
    },
    {
        "id": "snmp_community",
        "cat": "安全", "level": "中", "deduct": 8,
        "title": "SNMP 弱团体名",
        "pat": r"(?im)^\s*snmp-agent\s+community\s+(?:read|write)\s+(public|private)",
        "detail": "SNMP 使用 public/private 缺省团体名，可被任意主机读取设备信息。",
        "fix": ["snmp-agent community read <强口令> acl 2001"],
    },
    {
        "id": "no_mgmt_ip",
        "cat": "规范", "level": "高", "deduct": 12,
        "title": "无远程管理面",
        "pat_neg": r"(?im)^\s*interface\s+\S+\s*\n(?:\s*\n)*(?:.*\n)*?\s*ip\s+address\s+(?!127\.)\d",
        "detail": "除 Loopback 外无任何三层接口地址，无法远程管理，管理平面缺失。",
        "fix": ["interface Vlanif10", " ip address 172.16.10.1 255.255.255.0"],
    },
    {
        "id": "no_ntp",
        "cat": "规范", "level": "中", "deduct": 8,
        "title": "缺 NTP 时钟同步",
        "pat_neg": r"(?im)^\s*(?:ntp(?:-service)?\s+(?:server|service|unicast-server|unicast-peer)|clock\s+timezone)",
        "detail": "未配置时钟同步，日志时间不可信，故障回溯与日志对齐困难。",
        "fix": ["ntp-service unicast-server 172.16.10.10"],
    },
    {
        "id": "no_loghost",
        "cat": "规范", "level": "中", "deduct": 6,
        "title": "日志未远端留存",
        "pat_neg": r"(?im)^\s*(?:info-center\s+loghost|logging\s+(?:host|trap|buffered))",
        "detail": "日志仅本地留存，设备故障/被入侵后痕迹易丢失。",
        "fix": ["info-center loghost 172.16.10.10"],
    },
    {
        "id": "asset_default",
        "cat": "规范", "level": "低", "deduct": 4,
        "title": "资产信息不规范",
        "pat": r"(?im)^\s*(?:sysLocation\s+China|sysContact\s+400-810-9119)\s*$",
        "detail": "sysLocation/sysContact 为厂商缺省值，不利于故障定位与责任到人。",
        "fix": ["sysLocation 3F-机房A-机柜12", "sysContact 张三 138xxxx"],
    },
    {
        "id": "all_vlan1",
        "cat": "规范", "level": "中", "deduct": 10,
        "title": "缺省 VLAN 未划分",
        "pat_neg": r"(?im)^\s*vlan\s+(?!1\b)\d+",
        "detail": "未定义任何业务 VLAN，全部接口裸挂在缺省 VLAN 1，无业务/管理隔离。",
        "fix": ["vlan 10", " name Office", "vlan 20", " name Mgmt"],
    },
    {
        "id": "no_stp_guard",
        "cat": "稳定", "level": "中", "deduct": 10,
        "title": "无防环/环路防护",
        "pat_neg": r"(?im)^\s*(?:loopback-detection|stp\s+(?:enable|mode)|spanning-tree)",
        "detail": "未见生成树/环路防护配置，二层环境存在广播风暴风险。",
        "fix": ["stp enable", "loopback-detection enable"],
    },
    {
        "id": "no_storm",
        "cat": "稳定", "level": "低", "deduct": 5,
        "title": "无广播风暴抑制",
        "pat_neg": r"(?im)^\s*(?:storm-control|broadcast-suppression|port\s+isolate)",
        "detail": "未配置广播/组播抑制，单口异常流量可打满整机。",
        "fix": ["storm-control broadcast min-rate 100 max-rate 200"],
    },
    {
        "id": "no_portsec",
        "cat": "稳定", "level": "低", "deduct": 5,
        "title": "无端口安全",
        "pat_neg": r"(?im)^\s*(?:port\s+security|port-security|max-mac-count|mac-address\s+limit)",
        "detail": "接入侧未限制 MAC 学习数量，存在 MAC 洪泛与私接风险。",
        "fix": ["port-security enable", "port-security max-mac-count 2"],
    },
    {
        "id": "no_ssh",
        "cat": "安全", "level": "中", "deduct": 8,
        "title": "未启用 SSH",
        "pat_neg": r"(?im)^\s*(?:stelnet\s+server\s+enable|ssh\s+server\s+enable|ip\s+ssh\s+version)",
        "detail": "未见 SSH 服务配置，远程管理缺少加密通道。",
        "fix": ["stelnet server enable", "ssh user admin authentication-type password"],
    },
]

# 四维权重（总分 = 加权平均，固定不变 → 结果可复现）
WEIGHTS = {"安全": 0.35, "规范": 0.25, "容量": 0.15, "稳定": 0.25}


def _collect_evidence(text: str, pat: str, limit: int = 2) -> list[str]:
    out = []
    for m in re.finditer(pat, text):
        line = m.group(0).strip().splitlines()[0][:110]
        if line and line not in out:
            out.append(line)
        if len(out) >= limit:
            break
    return out


def score_inspect(version_text: str, interface_text: str, config_text: str) -> dict:
    """按固定规则给设备状态打分。

    同一份 (version, interface, config) 输入永远得到同样的分数与发现列表。
    """
    cfg = config_text or ""
    ver = version_text or ""
    iface = interface_text or ""

    findings: list[dict] = []
    ded = {"安全": 0.0, "规范": 0.0, "容量": 0.0, "稳定": 0.0}

    for r in RULES:
        hit = False
        evidence: list[str] = []
        if "pat" in r:
            evidence = _collect_evidence(cfg, r["pat"])
            hit = bool(evidence)
        else:
            # pat_neg：正则找不到任何匹配 → 判定为缺失该项配置
            hit = not re.search(r["pat_neg"], cfg)
            if hit:
                evidence = ["（配置中未找到对应条目）"]
        if hit:
            ded[r["cat"]] += r["deduct"]
            findings.append({
                "id": r["id"],
                "cat": r["cat"],
                "level": r["level"],
                "deduct": r["deduct"],
                "title": r["title"],
                "detail": r["detail"],
                "evidence": evidence,
                "fix": r["fix"],
            })

    # 运行时长（稳定）
    m = re.search(r"(?i)uptime is\s*(?:(\d+)\s*days?,\s*)?(?:(\d+)\s*hours?)?", ver)
    if m:
        days = int(m.group(1) or 0)
        hours = int(m.group(2) or 0)
        if days == 0 and hours < 24:
            ded["稳定"] += 4
            findings.append({
                "id": "short_uptime", "cat": "稳定", "level": "低", "deduct": 4,
                "title": "运行时间过短",
                "detail": f"Uptime 仅 {days} 天 {hours} 小时，冷启动原因不明，需确认是否掉电或配置丢失后恢复。",
                "evidence": [f"uptime is {days} days, {hours} hours"],
                "fix": ["display logbuffer | include RESTART"],
            })

    # CPU / 内存（容量）
    mc = re.search(r"(?i)(?:cpu(?:\s+usage)?|five seconds)[^\d]*(\d{1,3})\s*%", cfg + "\n" + iface)
    if mc and int(mc.group(1)) >= 80:
        ded["容量"] += 12
        findings.append({
            "id": "high_cpu", "cat": "容量", "level": "高", "deduct": 12,
            "title": "CPU 偏高",
            "detail": f"CPU 利用率 {mc.group(1)}%，接近阈值，转发面可能受影响。",
            "evidence": [mc.group(0)[:80]],
            "fix": ["display cpu-usage", "display process cpu"],
        })

    dims = {}
    for cat in ("安全", "规范", "容量", "稳定"):
        dims[cat] = int(max(0, min(100, 100 - ded[cat])))

    total = int(round(sum(dims[c] * WEIGHTS[c] for c in dims)))
    total = max(0, min(100, total))

    # 按严重度排序：高 → 中 → 低
    order = {"高": 0, "中": 1, "低": 2}
    findings.sort(key=lambda f: (order.get(f["level"], 9), -f["deduct"]))

    return {
        "total": total,
        "dims": dims,
        "findings": findings,
        "weights": WEIGHTS,
    }


def markdown_report(score: dict, analysis: str) -> str:
    """把确定性评分与 AI 分析拼成最终报告（分数由本函数写死，AI 不参与）。"""
    dims = score["dims"]
    lines = [
        f"## 总评分：{score['total']}/100",
        "## 四维评分",
        f"安全 {dims['安全']} · 规范 {dims['规范']} · 容量 {dims['容量']} · 稳定 {dims['稳定']}",
        "",
    ]
    return "\n".join(lines) + analysis
