"""检测输出结构化解析：把设备原始回显转成可直接渲染的表格 / 键值 / 仪表盘。

目标：界面不再只丢一坨原文。每一项检测都给出
  - summary：一句话汇总（如「4 个接口 · 2 UP / 2 DOWN」）
  - structured：可渲染的结构（table / kv / bars）
  - 原文始终保留在 result.output，供展开核对

解析策略是启发式的：优先按对齐列切分，再给每个单元格打状态色
（up/ok=绿、down/error=红、half/auto=黄），最后按 key 套用专项规则。
"""

import re

_TONE_OK = "ok"
_TONE_WARN = "warn"
_TONE_ERR = "error"
_TONE_INFO = "info"
_TONE_MUTED = "muted"

_OK_WORDS = {
    "up", "up/up", "full", "a-full", "f-full", "forwarding", "ok", "success",
    "enabled", "active", "normal", "master", "established", "full-duplex", "sfp",
}
_ERR_WORDS = {
    "down", "down/down", "err-disabled", "error", "failed", "fail", "disabled",
    "shutdown", "unreachable", "dropped", "discard", "invalid",
}
_WARN_WORDS = {
    "half", "a-half", "f-half", "listening", "blocking", "learning", "unknown",
    "auto", "standby", "backup", "init", "loading", "notconnect",
}

_IF_NAME_RE = re.compile(
    r"^(?:Gi|Te|Tw|Fo|Eth|GE|XGE|TenGig|GigabitEthernet|FastEthernet|Ethernet|"
    r"Vlan|Vlanif|Loopback|Tunnel|Serial|NULL|MEth|Bridge-Aggregation|"
    r"\d+/\d+(?:/\d+)?)[\w/.:-]*$",
    re.I,
)

# 真实 CLI 表头几乎总含这些列名关键词；用它把「表头」和散文区分开
_COL_LEXICON = {
    "interface", "port", "name", "status", "state", "type", "speed", "duplex",
    "vlan", "ip", "address", "mac", "protocol", "peer", "age", "time", "uptime",
    "route", "prefix", "nexthop", "metric", "cost", "prio", "priority", "role",
    "channel", "mode", "bandwidth", "util", "rx", "tx", "in", "out", "errors",
    "drops", "alias", "link", "admin", "oper", "desc", "description", "vrf",
    "area", "router-id", "neighbor", "rid", "uptime", "hold", "shr", "flags",
    "id", "vid", "tagged", "untagged", "learn", "forward", "discard",
}


# ---------------------------------------------------------------- 单元格着色
def tone_of(cell: str) -> str:
    """给单元格打状态色。"""
    s = (cell or "").strip()
    if not s:
        return _TONE_MUTED
    low = s.lower()

    # 百分比：按阈值上色
    m = re.fullmatch(r"(\d{1,3})\s*%", low)
    if m:
        v = int(m.group(1))
        return _TONE_ERR if v >= 95 else _TONE_WARN if v >= 80 else _TONE_OK

    # link/protocol 形如 UP/UP、UP/DOWN
    if "/" in low and all(p in (_OK_WORDS | _ERR_WORDS | _WARN_WORDS) for p in low.split("/")):
        parts = low.split("/")
        if all(p in _OK_WORDS for p in parts):
            return _TONE_OK
        if any(p in _ERR_WORDS for p in parts):
            return _TONE_ERR
        return _TONE_WARN

    if low in _OK_WORDS:
        return _TONE_OK
    if low in _ERR_WORDS:
        return _TONE_ERR
    if low in _WARN_WORDS:
        return _TONE_WARN
    if re.search(r"(?i)(?:^|[^a-z])(?:err|fail|down|deny|refuse|timeout)(?:[^a-z]|$)", low):
        return _TONE_ERR
    return _TONE_INFO


# ---------------------------------------------------------------- 列切分
def _split(line: str, min_sp: int) -> list[str]:
    return [c.strip() for c in re.split(rf"\s{{{min_sp},}}", line.strip()) if c.strip()]


def _pick_split(header: str, body_lines: list[str]) -> int:
    """选使数据行列数与表头最一致的分隔宽度（1 或 2 个以上空格）。"""
    best, best_score = 2, -1.0
    for min_sp in (2, 1):
        h = _split(header, min_sp)
        if len(h) < 2:
            continue
        hit = sum(1 for ln in body_lines if len(_split(ln, min_sp)) == len(h))
        score = hit / max(len(body_lines), 1)
        if score > best_score:
            best, best_score = min_sp, score
    return best


# ---------------------------------------------------------------- 表头识别
def _find_header(lines: list[str]) -> int | None:
    """找表头行：含列名词典里的关键词、多为单词、后面跟着像数据的行。"""
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or len(s) < 4 or len(s) > 120:
            continue
        toks = re.split(r"\s+", s)
        if len(toks) < 2 or len(toks) > 12:
            continue
        # 表头里基本不含独立数字/接口名
        alpha = sum(1 for t in toks if re.match(r"^[A-Za-z][\w/\-]*$", t))
        if alpha < len(toks) * 0.7:
            continue
        # 必须命中列名词典，否则当散文处理（如 "Huawei Versatile Routing Platform Software"）
        hits = sum(1 for t in toks if t.lower().strip(",:") in _COL_LEXICON)
        if hits < 1:
            continue
        # 单个词长度别太长，散文里的长词很多
        if max((len(t) for t in toks), default=0) > 18:
            continue
        # 后续至少有一行是数据
        after = [l for l in lines[i + 1: i + 8] if l.strip()]
        if not after:
            continue
        dataish = sum(1 for l in after if len(_split(l, 1)) >= 2 and re.search(r"\d", l))
        if dataish >= max(1, len(after) // 2):
            return i
    return None


# ---------------------------------------------------------------- 表格解析
def _parse_table(text: str, max_rows: int = 60) -> dict | None:
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    hi = _find_header(lines)
    if hi is None:
        return None

    header_line = lines[hi]
    # 表头可能折行（如 "Interface Link/Protocol Speed  Duplex Vlan" / "Type  Alias Name"）
    header = _split(header_line, 1)
    extra = hi + 1
    while extra < len(lines):
        nxt = lines[extra]
        toks = re.split(r"\s+", nxt.strip())
        if toks and all(re.match(r"^[A-Za-z][\w /\-]*$", t) for t in toks) and not _IF_NAME_RE.match(nxt.strip()):
            header += toks
            extra += 1
        else:
            break

    body = lines[extra:]
    min_sp = _pick_split(header_line, body[:20])
    ncols = len(_split(header_line, min_sp)) or len(header)

    rows: list[list[dict]] = []
    for ln in body[: max_rows * 2]:
        cells = _split(ln, min_sp)
        if not cells:
            continue
        # 纯提示/说明行（Codes: ... 等）跳过
        if re.match(r"(?i)^(codes?|note|total|---|\+\+)", ln.strip()):
            continue
        if len(cells) == 1 and rows:
            # 折行续行（如接口 Type "G-TX"）并入上一行
            rows[-1].append({"text": cells[0], "tone": tone_of(cells[0])})
            continue
        rows.append([{"text": c, "tone": tone_of(c)} for c in cells])
        if len(rows) >= max_rows:
            break

    if not rows:
        return None

    # 列数对齐到表头（多余合并进末列，不足补空）
    width = max(len(r) for r in rows)
    cols = header[:width] if len(header) >= width else header + [f"列{i+1}" for i in range(len(header), width)]
    norm = []
    for r in rows:
        if len(r) > len(cols):
            tail = " ".join(c["text"] for c in r[len(cols) - 1:])
            r = r[: len(cols) - 1] + [{"text": tail, "tone": tone_of(tail)}]
        while len(r) < len(cols):
            r.append({"text": "", "tone": _TONE_MUTED})
        norm.append(r)

    return {"type": "table", "columns": cols, "rows": norm}


# ---------------------------------------------------------------- 键值解析
def _parse_kv(text: str) -> dict | None:
    pairs = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or len(s) > 160:
            continue
        m = re.match(r"^([^:：=]{2,40})\s*[:：=]\s*(.+)$", s)
        if m:
            k, v = m.group(1).strip(), m.group(2).strip()
            if v:
                pairs.append({"k": k, "v": v, "tone": tone_of(v)})
    if len(pairs) < 2:
        return None
    return {"type": "kv", "pairs": pairs[:40]}


# ---------------------------------------------------------------- 仪表盘解析
def _parse_bars(text: str) -> dict | None:
    bars = []
    for ln in text.splitlines():
        m = re.search(
            r"(?i)(cpu(?:\s*usage)?|memory|mem(?:ory)?\s*usage|内存|cpu利用率|温度|temperature)"
            r"[^\d%]{0,20}(\d{1,3})\s*%",
            ln,
        )
        if m:
            label = m.group(1).strip()
            val = int(m.group(2))
            bars.append({
                "label": label,
                "value": val,
                "max": 100,
                "tone": _TONE_ERR if val >= 95 else _TONE_WARN if val >= 80 else _TONE_OK,
            })
    if not bars:
        return None
    return {"type": "bars", "bars": bars}


# ---------------------------------------------------------------- 日志解析
def _parse_logs(text: str) -> dict | None:
    rows = []
    for ln in text.splitlines():
        s = ln.strip()
        if len(s) < 8:
            continue
        low = s.lower()
        if re.search(r"(?i)(?:crit|emerg|alert|error|err\b|fail|down|flap|link-down|%link|%lineproto)", low):
            tone = _TONE_ERR
        elif re.search(r"(?i)(?:warn|notice|timeout|retry|discard|drop)", low):
            tone = _TONE_WARN
        else:
            tone = _TONE_MUTED
        rows.append({"text": s[:220], "tone": tone})
        if len(rows) >= 50:
            break
    if len(rows) < 2:
        return None
    bad = sum(1 for r in rows if r["tone"] == _TONE_ERR)
    return {"type": "logs", "rows": rows, "bad": bad}


# ---------------------------------------------------------------- 汇总
def _summary_of(struct: dict) -> str:
    if struct.get("type") == "table":
        rows, cols = struct["rows"], struct["columns"]
        # 找状态列（含 up/down 的列）
        status_idx = None
        for i, c in enumerate(cols):
            toks = " ".join(r[i]["text"] for r in rows[:6]).lower()
            if re.search(r"\b(up|down)\b", toks):
                status_idx = i
                break
        if status_idx is not None:
            ups = sum(1 for r in rows if tone_of(r[status_idx]["text"]) == _TONE_OK)
            downs = sum(1 for r in rows if tone_of(r[status_idx]["text"]) == _TONE_ERR)
            return f"共 {len(rows)} 行 · {ups} 正常 / {downs} 异常"
        return f"共 {len(rows)} 行 · {len(cols)} 列"
    if struct.get("type") == "kv":
        return f"解析到 {len(struct['pairs'])} 个字段"
    if struct.get("type") == "bars":
        return " · ".join(f"{b['label']} {b['value']}%" for b in struct["bars"])
    if struct.get("type") == "logs":
        return f"共 {len(struct['rows'])} 行 · {struct['bad']} 行异常"
    return ""


# ---------------------------------------------------------------- 版本信息
def _parse_version(text: str) -> dict | None:
    """提取版本/型号/运行时长/内存等关键字段。"""
    pairs = []
    def add(k, v):
        if v:
            pairs.append({"k": k, "v": str(v).strip()[:80], "tone": tone_of(str(v))})

    m = re.search(r"(?i)(?:VRP.*?Version|IOS.*?Version|Software.*?Version|SW Version|Version)\s*[^\dA-Za-z]*(V?[\w.\(\)]+)", text)
    if m:
        add("软件版本", m.group(1))
    m = re.search(r"(?i)(?:^|\s)(\S+\s+\d+[A-Z\-/]*(?:-\w+)*)\s+(?:uptime is|Uptime)", text)
    if not m:
        m = re.search(r"(?i)^(\S+)\s+uptime is", text, re.M)
    if m:
        add("设备型号", m.group(1))
    m = re.search(r"(?i)uptime is\s*(.+)", text)
    if m:
        add("运行时长", m.group(1).strip()[:48])
    for label, pat in (
        ("SDRAM", r"(?i)SDRAM\s*[:：]?\s*([\d]+\s*\w+)"),
        ("Flash", r"(?i)Flash\s*[:：]?\s*([\d]+\s*\w+)"),
        ("内存", r"(?i)Memory\s*[:：]?\s*([\d]+\s*\w+)"),
    ):
        m = re.search(pat, text)
        if m:
            add(label, m.group(1))
    if len(pairs) < 2:
        return None
    return {"type": "kv", "pairs": pairs}


# ---------------------------------------------------------------- 入口
def parse_structured(key: str, output: str) -> dict:
    """把原始回显解析成可渲染结构。解析不出时退化为行列表。"""
    text = output or ""
    if not text.strip():
        return {"type": "lines", "rows": [], "summary": "无输出"}

    struct = None
    # 专项优先
    if key == "version":
        struct = _parse_version(text)
    if struct is None and (key == "cpu" or re.search(r"(?i)cpu\s*(usage|util|利用率)|memory\s*(usage|util)", text)):
        struct = _parse_bars(text)
    if struct is None and key == "log":
        struct = _parse_logs(text)
    # 有 ≥3 个 key:value 时优先当键值（散文/版本信息不该被当表格）
    if struct is None:
        kv = _parse_kv(text)
        if kv and len(kv["pairs"]) >= 3:
            struct = kv
    if struct is None:
        struct = _parse_table(text)
    if struct is None:
        struct = _parse_kv(text)
    if struct is None:
        struct = _parse_bars(text)
    if struct is None:
        struct = _parse_logs(text)
    if struct is None:
        rows = [{"text": l.strip()[:220], "tone": tone_of(l)} for l in text.splitlines() if l.strip()][:60]
        struct = {"type": "lines", "rows": rows}

    struct["summary"] = _summary_of(struct)
    return struct
