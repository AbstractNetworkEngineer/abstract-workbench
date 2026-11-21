"""设备运维检测站：检测项可自定义（名称/命令/分组）+ 状态判定 + 指标提取。

检测项分两档：
1. 内置项 —— 首次启动生成，覆盖常见协议/状态；可改可停用，但不会被误删到无法恢复
   （管理页有「恢复内置」按钮）。
2. 自定义项 —— 用户自己填展示名与查看命令，按厂商方言写两条（display 风格 / show 风格）。
   自定义项走通用分析器：按输出是否为空、行数、IP/MAC 计数、异常关键词给判定。
"""

import re
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from connectors import ConnectorError, get_dialect
from models import AuditLog, DetectItem, Device
from services.detect_parse import parse_structured
from services.executor import execute_on_device, serial_hint

# 内置检测项（首次启动生成入库；cmd_display=华为/H3C，cmd_show=DCN/Cisco/通用）
BUILTIN_ITEMS = [
    {"key": "version", "label": "设备版本", "cat": "基础信息", "cmd_display": "display version", "cmd_show": "show version", "sort": 10},
    {"key": "int_brief", "label": "接口状态", "cat": "接口", "cmd_display": "display ip interface brief", "cmd_show": "show ip interface brief", "sort": 20},
    {"key": "int_counters", "label": "接口计数", "cat": "接口", "cmd_display": "display interface", "cmd_show": "show interfaces", "sort": 21},
    {"key": "vlan", "label": "VLAN 数据", "cat": "二层协议", "cmd_display": "display vlan", "cmd_show": "show vlan", "sort": 30},
    {"key": "mac", "label": "MAC 表", "cat": "二层协议", "cmd_display": "display mac-address", "cmd_show": "show mac-address-table", "sort": 31},
    {"key": "stp", "label": "生成树 STP", "cat": "二层协议", "cmd_display": "display stp brief", "cmd_show": "show spanning-tree summary", "sort": 32},
    {"key": "route", "label": "路由表", "cat": "三层协议", "cmd_display": "display ip routing-table", "cmd_show": "show ip route", "sort": 40},
    {"key": "arp", "label": "ARP 表", "cat": "三层协议", "cmd_display": "display arp", "cmd_show": "show arp", "sort": 41},
    {"key": "ospf", "label": "OSPF 邻居", "cat": "三层协议", "cmd_display": "display ospf peer brief", "cmd_show": "show ip ospf neighbor", "sort": 42},
    {"key": "rip", "label": "RIP 状态", "cat": "三层协议", "cmd_display": "display rip", "cmd_show": "show ip rip", "sort": 43},
    {"key": "dhcp", "label": "DHCP 服务", "cat": "服务", "cmd_display": "display ip pool", "cmd_show": "show ip dhcp binding", "sort": 50},
    {"key": "cpu", "label": "CPU / 内存", "cat": "系统", "cmd_display": "display cpu-usage", "cmd_show": "show processes cpu", "sort": 60},
    {"key": "log", "label": "系统日志", "cat": "系统", "cmd_display": "display logbuffer", "cmd_show": "show logging", "sort": 61},
]

NA_MARKERS = ("unrecognized", "invalid input", "unknown command", "wrong parameter", "not supported")


def ensure_detect_items(db: Session) -> None:
    """首次启动生成内置检测项；已存在则跳过。"""
    if db.query(DetectItem).count() > 0:
        return
    for it in BUILTIN_ITEMS:
        db.add(DetectItem(
            key=it["key"], label=it["label"], cat=it["cat"],
            cmd_display=it["cmd_display"], cmd_show=it["cmd_show"],
            builtin=True, enabled=True, sort=it["sort"],
        ))
    db.commit()


def reset_builtin_items(db: Session) -> int:
    """恢复内置项：把内置项重置为默认命令/名称，缺失的补回来。返回补齐数量。"""
    existing = {i.key: i for i in db.query(DetectItem).all()}
    added = 0
    for it in BUILTIN_ITEMS:
        row = existing.get(it["key"])
        if row is None:
            db.add(DetectItem(
                key=it["key"], label=it["label"], cat=it["cat"],
                cmd_display=it["cmd_display"], cmd_show=it["cmd_show"],
                builtin=True, enabled=True, sort=it["sort"],
            ))
            added += 1
        else:
            row.label = it["label"]
            row.cat = it["cat"]
            row.cmd_display = it["cmd_display"]
            row.cmd_show = it["cmd_show"]
            row.builtin = True
            row.enabled = True
            row.sort = it["sort"]
    db.commit()
    return added


def _cmd_of(item: DetectItem, dialect_name: str) -> str:
    if dialect_name in ("huawei", "h3c"):
        return (item.cmd_display or item.cmd_show or "").strip()
    return (item.cmd_show or item.cmd_display or "").strip()


def analyze_generic(output: str, key: str = "") -> dict:
    """自定义检测项的通用判定：按输出规模 / 关键实体 / 异常词给状态，并附结构化视图。"""
    text = output or ""
    if not text.strip():
        return {"status": "na", "metrics": {}, "note": "无输出（命令可能不被支持）",
                "structured": parse_structured(key, text)}
    low = text.lower()
    if any(m in low for m in NA_MARKERS):
        return {"status": "na", "metrics": {}, "note": "设备不支持该命令",
                "structured": parse_structured(key, text)}

    metrics: dict[str, object] = {}
    lines = [l for l in text.splitlines() if l.strip()]
    metrics["有效行数"] = len(lines)

    ips = set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text))
    if ips:
        metrics["IP 数"] = len(ips)
    macs = set(re.findall(r"(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}|(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}", text, re.I))
    if macs:
        metrics["MAC 数"] = len(macs)

    bad = len(re.findall(r"(?i)(?<!no )errors?|failed|down|drop|flap", text))
    metrics["异常关键词"] = bad

    structured = parse_structured(key, text)
    if bad >= 5:
        return {"status": "warn", "metrics": metrics, "note": f"{bad} 行含异常关键词", "structured": structured}
    return {"status": "ok", "metrics": metrics, "note": "", "structured": structured}


def analyze(key: str, output: str) -> dict:
    """内置项的专项判定 + 自定义项回退到通用判定。status: ok / warn / error / na

    每条结果都带 structured（表格/键值/仪表盘/日志视图），界面据此渲染状态视图；
    原文保留在 result.output，供展开核对。
    """
    text = output or ""
    low = text.lower()
    structured = parse_structured(key, text)
    if not text.strip() or any(m in low for m in NA_MARKERS):
        return {"status": "na", "metrics": {}, "note": "设备不支持或无输出", "structured": structured}

    metrics: dict = {}
    status = "ok"
    note = ""

    if key == "version":
        m = re.search(r"(?:uptime is|Uptime is)\s*(.+)", text)
        if m:
            metrics["运行时长"] = m.group(1).strip()[:40]
        m2 = re.search(r"(?:Version|VRP.*?Version)\s*[^\d]*(V?[\w.\(\)]+)", text)
        if m2:
            metrics["软件版本"] = m2.group(1)[:24]

    elif key == "int_brief":
        lines = [ln for ln in text.splitlines() if re.search(r"\d+\.\d+\.\d+\.\d+|unassigned", ln)]
        ups = sum(1 for ln in lines if re.search(r"\bup\s+up\b", ln, re.I))
        downs = sum(1 for ln in lines if re.search(r"\bdown\b", ln, re.I))
        metrics["接口总数"] = len(lines) or len(text.splitlines())
        metrics["UP"] = ups
        metrics["DOWN"] = downs
        status = "ok" if ups else "warn"
        note = f"{ups} 个接口 UP"

    elif key == "int_counters":
        # 用结构化结果统计真实接口行，比数段落标题靠谱
        rows = structured.get("rows") or [] if structured.get("type") == "table" else []
        metrics["接口数"] = len(rows)
        ups = sum(1 for r in rows if r and str(r[1].get("text", "")).upper().startswith("UP") if len(r) > 1)
        metrics["UP"] = ups
        err = len(re.findall(r"error|drop", text, re.I))
        metrics["错误/丢包关键词"] = err
        if err > 20:
            status = "warn"
            note = "存在较多错误/丢包计数"

    elif key in ("mac", "arp", "route"):
        mac_re = r"(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}|(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}"
        rows = [
            ln for ln in text.splitlines()
            if re.search(r"\d+\.\d+\.\d+\.\d+|" + mac_re, ln, re.I)
        ]
        metrics["条目数"] = len(rows)
        if not rows:
            status = "warn"
            note = "表项为空"

    elif key == "vlan":
        rows = set(re.findall(r"(?i)vlan\s*(?:id)?\s*[:：]?\s*(\d{1,4})", text))
        metrics["VLAN 数"] = len(rows)

    elif key == "stp":
        m = re.search(r"(?i)(?:root|this switch)", text)
        metrics["STP 实例"] = len(re.findall(r"(?i)instance|vlan\s*\d+", text))
        if "this switch" in low:
            note = "本机为根桥"
        if "error" in low or "disabled" in low:
            status = "warn"

    elif key in ("ospf", "rip"):
        rows = re.findall(r"\d+\.\d+\.\d+\.\d+", text)
        metrics["邻居/条目数"] = len(rows)
        if key == "ospf" and not rows:
            status = "warn"
            note = "无 OSPF 邻居"
        if key == "rip":
            metrics["RIP 进程"] = len(re.findall(r"(?i)process|rip\s+\d+", text))

    elif key == "dhcp":
        rows = re.findall(r"\d+\.\d+\.\d+\.\d+", text)
        metrics["绑定/地址数"] = len(rows)

    elif key == "cpu":
        m = re.search(r"(?i)(?:cpu(?:\s+usage)?|five seconds)[^\d]*(\d{1,2})\s*%", text)
        if m:
            metrics["CPU%"] = int(m.group(1))
            if int(m.group(1)) > 70:
                status = "warn"
                note = "CPU 偏高"
        m2 = re.search(r"(?i)memory[^\d]*(\d{1,2})\s*%", text)
        if m2:
            metrics["内存%"] = int(m2.group(1))

    elif key == "log":
        bad = len(re.findall(r"(?i)(?<!no )errors?|failed|flap|changed state to down|link-down", text))
        metrics["异常日志行"] = bad
        if bad:
            status = "warn"
            note = f"{bad} 行异常日志"

    else:
        # 自定义项：通用判定
        return analyze_generic(output, key)

    return {"status": status, "metrics": metrics, "note": note, "structured": structured}


def catalog(db: Session, only_enabled: bool = False) -> list[dict]:
    """返回检测项清单（内置 + 自定义）。"""
    ensure_detect_items(db)
    q = db.query(DetectItem).order_by(DetectItem.sort, DetectItem.id)
    if only_enabled:
        q = q.filter(DetectItem.enabled.is_(True))
    return [
        {
            "id": r.id,
            "key": r.key,
            "label": r.label,
            "cat": r.cat,
            "cmd_display": r.cmd_display,
            "cmd_show": r.cmd_show,
            "builtin": bool(r.builtin),
            "enabled": bool(r.enabled),
            "sort": r.sort,
        }
        for r in q.all()
    ]


def run_detect(db: Session, device_id: int, keys: list[str] | None = None) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "设备不存在")

    ensure_detect_items(db)
    dialect = get_dialect(device.vendor)
    rows = db.query(DetectItem).filter(DetectItem.enabled.is_(True)).order_by(DetectItem.sort, DetectItem.id).all()
    selected = [r for r in rows if not keys or r.key in keys]
    if not selected:
        raise HTTPException(400, "没有可执行的检测项")

    t0 = time.time()
    # 只保留有命令的项
    runnable = [r for r in selected if _cmd_of(r, dialect.name)]
    skipped = [r for r in selected if not _cmd_of(r, dialect.name)]
    commands = [_cmd_of(r, dialect.name) for r in runnable]

    try:
        raw, via = execute_on_device(device, commands, timeout_each=20.0) if commands else ([], "none")
    except ConnectorError as e:
        raise HTTPException(502, f"连接设备失败：{e}{serial_hint(device)}") from e
    out_map = {r["command"]: r for r in raw}

    results = []
    for item in runnable:
        cmd = _cmd_of(item, dialect.name)
        r = out_map.get(cmd, {"command": cmd, "output": "", "ok": False})
        verdict = analyze(item.key, r.get("output") or "")
        results.append({
            "key": item.key,
            "label": item.label,
            "cat": item.cat,
            "command": cmd,
            "output": (r.get("output") or "")[:8000],
            "ok": r.get("ok", False),
            "custom": not bool(item.builtin),
            **verdict,
        })
    for item in skipped:
        results.append({
            "key": item.key, "label": item.label, "cat": item.cat, "command": "",
            "output": "", "ok": False, "custom": not bool(item.builtin),
            "status": "na", "metrics": {}, "note": "未填写该方言的命令，已跳过",
        })

    db.add(AuditLog(
        kind="detect", device_id=device.id, device_name=device.name,
        action="运维检测站", detail=f"items={len(results)}, via={via}",
        status="ok",
    ))
    db.commit()

    return {
        "device": {"id": device.id, "name": device.name, "vendor": dialect.label},
        "via": via,
        "elapsed": round(time.time() - t0, 1),
        "results": results,
    }
