"""Wireshark 接入层：用 tshark / dumpcap / capinfos 做抓包与协议分析。

Wireshark 的可编程接口是它的命令行套件，不是 GUI：
  - dumpcap   抓包（Npcap 驱动，需管理员或已授权）
  - tshark    离线分析（协议分层 / 会话 / 端点 / 专家信息 / 过滤）
  - capinfos  文件元信息（包数、时长、起止时间）
  - Wireshark GUI  仅用于「一键深挖」，调用其 exe 打开 pcap

本模块只负责把这些 CLI 包一层，不碰抓包原理。
"""

import os
import re
import signal
import shutil
import subprocess
import time
from pathlib import Path

from database import DATA_DIR

CAPTURE_DIR = DATA_DIR / "captures"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

# Wireshark 安装目录：环境变量优先，其次常见路径
_ENV_KEYS = ("WIRESHARK_HOME", "WIRESHARK_PATH", "WIRESHARK_DIR")
_COMMON = [
    r"C:\Program Files\Wireshark",
    r"C:\Program Files (x86)\Wireshark",
    r"C:\Program Files\Wireshark-4.4.5",
    "/usr/bin",
    "/usr/local/bin",
    "/opt/wireshark/bin",
    "/Applications/Wireshark.app/Contents/MacOS",
]

# 正在进行的抓包会话：{session_id: {...}}
_sessions: dict[str, dict] = {}
_seq = 0


def _find_tool(name: str) -> str | None:
    """找 Wireshark 套件里的某个可执行文件。"""
    exe = name + (".exe" if os.name == "nt" else "")
    for key in _ENV_KEYS:
        v = os.environ.get(key, "")
        if v:
            p = Path(v) / exe
            if p.exists():
                return str(p)
    for d in _COMMON:
        p = Path(d) / exe
        if p.exists():
            return str(p)
    found = shutil.which(name) or shutil.which(exe)
    return found


def wireshark_status() -> dict:
    """Wireshark 接入自检：哪些工具可用、抓包驱动是否就绪。"""
    tools = {
        "tshark": _find_tool("tshark"),
        "dumpcap": _find_tool("dumpcap"),
        "capinfos": _find_tool("capinfos"),
        "wireshark": _find_tool("wireshark"),
    }
    version = ""
    if tools["tshark"]:
        try:
            out = _run_cli([tools["tshark"], "-v"], timeout=15)
            m = re.search(r"TShark \(Wireshark\)\s+([\d.]+)", out)
            version = m.group(1) if m else (out.splitlines() or [""])[0][:60]
        except Exception as e:  # noqa: BLE001
            version = f"读取失败: {e}"
    ready = bool(tools["tshark"] and tools["dumpcap"])
    return {
        "ready": ready,
        "version": version,
        "tools": {k: bool(v) for k, v in tools.items()},
        "paths": tools,
        "capture_dir": str(CAPTURE_DIR),
        "hint": "" if ready else "未找到 tshark/dumpcap，请安装 Wireshark（含 Npcap）。",
    }


def list_interfaces() -> list[dict]:
    """可抓包网卡：dumpcap -D。"""
    dumpcap = _find_tool("dumpcap")
    if not dumpcap:
        return []
    try:
        out = _run_cli([dumpcap, "-D"], timeout=20)
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for ln in out.splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(\S+)\s+\((.+)\)\s*$", ln.strip())
        if m:
            rows.append({
                "index": int(m.group(1)),
                "device": m.group(2),
                "name": m.group(3),
            })
    return rows


def _popen_capture(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=(0x00000008 if os.name == "nt" else 0),  # CREATE_NO_WINDOW
    )


def _run_cli(args: list[str], timeout: int = 120) -> str:
    """跑 Wireshark 套件的子命令，**固定按 UTF-8 解码输出**。

    Wireshark 4.x 输出 UTF-8；中文 Windows 的 locale 是 GBK，
    用 text=True 会按 GBK 解码直接抛 UnicodeDecodeError，导致输出全丢
    （打包版尤其明显，因为那时没 PYTHONUTF8）。所以这里显式指定编码。
    """
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=(0x00000008 if os.name == "nt" else 0),
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"执行 {Path(args[0]).name} 失败: {e}") from e
    out = (r.stdout or b"") + b"\n" + (r.stderr or b"")
    return out.decode("utf-8", errors="replace")


def start_capture(iface: str, bpf_filter: str = "", max_packets: int = 20000,
                  duration: int = 60, name: str = "") -> dict:
    """开始抓包，返回会话信息。dumpcap 后台跑，写 pcapng 到 captures/。"""
    global _seq
    dumpcap = _find_tool("dumpcap")
    if not dumpcap:
        raise RuntimeError("未找到 dumpcap（Wireshark 未安装或不在默认路径）")

    iface = (iface or "").strip()
    if not iface:
        raise RuntimeError("未指定网卡")

    _seq += 1
    sid = f"cap{_seq}_{int(time.time())}"
    fname = f"{(name or 'capture').replace('/', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.pcapng"
    out_path = CAPTURE_DIR / fname

    args = [dumpcap, "-i", iface, "-w", str(out_path), "-q"]
    if bpf_filter and bpf_filter.strip():
        args += ["-f", bpf_filter.strip()]
    if max_packets and max_packets > 0:
        args += ["-c", str(int(max_packets))]
    if duration and duration > 0:
        args += ["-a", f"duration:{int(duration)}"]

    try:
        proc = _popen_capture(args)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"启动 dumpcap 失败: {e}") from e

    info = {
        "id": sid,
        "iface": iface,
        "filter": (bpf_filter or "").strip(),
        "file": str(out_path),
        "filename": fname,
        "max_packets": max_packets,
        "duration": duration,
        "started_at": time.time(),
        "pid": proc.pid,
        "proc": proc,
        "status": "running",
    }
    _sessions[sid] = info
    return _public(info)


def _public(info: dict) -> dict:
    return {k: v for k, v in info.items() if k not in ("proc",)}


def capture_status(sid: str) -> dict:
    info = _sessions.get(sid)
    if not info:
        raise RuntimeError("抓包会话不存在或已清理")
    proc: subprocess.Popen = info["proc"]
    if proc.poll() is not None:
        info["status"] = "stopped"
        info["exit_code"] = proc.returncode
    else:
        info["status"] = "running"
    p = Path(info["file"])
    info["file_size"] = p.stat().st_size if p.exists() else 0
    info["elapsed"] = round(time.time() - info["started_at"], 1)
    return _public(info)


def stop_capture(sid: str) -> dict:
    info = _sessions.get(sid)
    if not info:
        raise RuntimeError("抓包会话不存在")
    proc: subprocess.Popen = info["proc"]
    if proc.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, timeout=10,
                )
            else:
                os.kill(proc.pid, signal.SIGINT)
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=8)
        except Exception:  # noqa: BLE001
            pass
    info["status"] = "stopped"
    p = Path(info["file"])
    info["file_size"] = p.stat().st_size if p.exists() else 0
    return _public(info)


def list_sessions() -> list[dict]:
    out = []
    for sid in list(_sessions):
        try:
            out.append(capture_status(sid))
        except Exception:  # noqa: BLE001
            continue
    return out


# ---------------------------------------------------------------- 文件管理
def list_captures() -> list[dict]:
    rows = []
    for p in sorted(CAPTURE_DIR.glob("*.pcapng"), reverse=True):
        rows.append({
            "filename": p.name,
            "path": str(p),
            "size": p.stat().st_size,
            "mtime": int(p.stat().st_mtime),
        })
    for p in sorted(CAPTURE_DIR.glob("*.pcap"), reverse=True):
        rows.append({
            "filename": p.name,
            "path": str(p),
            "size": p.stat().st_size,
            "mtime": int(p.stat().st_mtime),
        })
    rows.sort(key=lambda r: -r["mtime"])
    return rows


def _resolve(path: str) -> Path:
    """限定在 captures 目录内，防止任意路径读取。"""
    p = Path(path).resolve()
    root = CAPTURE_DIR.resolve()
    if not str(p).startswith(str(root)):
        # 也接受文件名
        cand = CAPTURE_DIR / Path(path).name
        if cand.exists():
            return cand
        raise RuntimeError("只允许分析 captures 目录内的抓包文件")
    if not p.exists():
        raise RuntimeError("抓包文件不存在")
    return p


def _run_tshark(args: list[str], timeout: int = 120) -> str:
    tshark = _find_tool("tshark")
    if not tshark:
        raise RuntimeError("未找到 tshark")
    return _run_cli([tshark, *args], timeout=timeout)


# ---------------------------------------------------------------- 统计解析
_UNIT = {"byte": 1, "bytes": 1, "kb": 1024, "kib": 1024, "mb": 1024 ** 2,
         "mib": 1024 ** 2, "gb": 1024 ** 3, "gib": 1024 ** 3, "tb": 1024 ** 4}


def _eat_size(tokens: list[str], i: int) -> tuple[int, int]:
    """吃掉 "111 kB" / "36 bytes" / "268" 这样的 数值+单位，返回 (字节数, 新下标)。"""
    if i >= len(tokens):
        return 0, i
    try:
        num = float(tokens[i].replace(",", ""))
    except ValueError:
        return 0, i + 1
    i += 1
    if i < len(tokens) and tokens[i].lower() in _UNIT:
        num *= _UNIT[tokens[i].lower()]
        i += 1
    return int(num), i


def _eat_int(tokens: list[str], i: int) -> tuple[int, int]:
    if i >= len(tokens):
        return 0, i
    try:
        return int(float(tokens[i].replace(",", ""))), i + 1
    except ValueError:
        return 0, i + 1


def _parse_io_phs(text: str) -> list[dict]:
    """tshark -z io,phs 的协议分层统计。"""
    rows = []
    for ln in text.splitlines():
        # "    eth                                      frames:12 bytes:800"
        m = re.match(r"^(\s+)(\S+)\s+frames:(\d+)\s+bytes:(\d+)", ln)
        if m:
            depth = len(m.group(1)) // 4
            rows.append({
                "proto": m.group(2),
                "frames": int(m.group(3)),
                "bytes": int(m.group(4)),
                "depth": max(0, depth - 1),
            })
    return rows


def _parse_conv(text: str, kind: str = "ip") -> list[dict]:
    """tshark -z conv,ip 的会话表。

    行形如：`127.0.0.1  <-> 127.0.0.1  0 0 bytes  268 111 kB  268 111 kB  0.000000  7.0568`
    即 <-帧数 <-字节  ->帧数 ->字节  总帧数 总字节  相对起始  时长
    """
    rows = []
    for ln in text.splitlines():
        s = ln.strip()
        if "<->" not in s:
            continue
        m = re.match(r"^(.+?)\s+<->\s+(.+?)\s+(.*)$", s)
        if not m:
            continue
        left, right, tail = m.group(1).strip(), m.group(2).strip(), m.group(3)
        tokens = tail.split()
        i = 0
        _, i = _eat_int(tokens, i)          # <- frames
        _, i = _eat_size(tokens, i)         # <- bytes
        _, i = _eat_int(tokens, i)          # -> frames
        _, i = _eat_size(tokens, i)         # -> bytes
        frames, i = _eat_int(tokens, i)     # total frames
        nbytes, i = _eat_size(tokens, i)    # total bytes
        duration = 0.0
        # 后面两个是 相对起始 / 时长（浮点）
        floats = []
        while i < len(tokens):
            try:
                floats.append(float(tokens[i].replace(",", "")))
            except ValueError:
                break
            i += 1
        if len(floats) >= 2:
            duration = floats[-1]
        elif len(floats) == 1:
            duration = floats[0]
        rows.append({
            "pair": f"{left}  ↔  {right}",
            "frames": frames,
            "bytes": nbytes,
            "duration": round(duration, 4),
        })
    rows.sort(key=lambda r: -r["bytes"])
    return rows


def _parse_endpoints(text: str) -> list[dict]:
    """tshark -z endpoints,ip 的端点表。

    表头是 `| Packets | | Bytes | ...`，数据行：地址 + 7 个数字。
    """
    rows = []
    started = False
    for ln in text.splitlines():
        s = ln.strip()
        if set(s) <= {"=", "-", " ", "|", "+"} and s:
            started = True
            continue
        if not started or not s:
            continue
        if re.search(r"(?i)packets|bytes|address|filter:", s) and not re.match(r"^\d", s.split()[0] if s.split() else ""):
            if "<->" in s or "|" in s:
                continue
        tokens = s.split()
        if len(tokens) < 3:
            continue
        addr = tokens[0]
        if not re.match(r"^[\d.:a-fA-F]+$", addr):
            continue
        try:
            rows.append({
                "address": addr,
                "frames": int(float(tokens[1].replace(",", ""))),
                "bytes": int(float(tokens[2].replace(",", ""))),
            })
        except ValueError:
            continue
        if len(rows) > 40:
            break
    rows.sort(key=lambda r: -r["bytes"])
    return rows


def _parse_expert(text: str) -> list[dict]:
    rows = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        m = re.match(r"(?i)^(Errors|Warnings|Notes|Chats|Error|Warning|Note|Chat)\b(.*)$", s)
        if m:
            lvl = m.group(1).rstrip(":")
            rest = m.group(2)
            cm = re.search(r"(\d[\d\s]*)", rest)
            rows.append({
                "level": lvl,
                "count": int(cm.group(1).replace(" ", "")) if cm else 0,
                "raw": s[:140],
            })
    return rows


def analyze_pcap(path: str, conv_kind: str = "ip") -> dict:
    """离线分析一个抓包文件：元信息 + 协议分层 + 会话 + 端点 + 专家信息。"""
    p = _resolve(path)

    # 元信息
    meta = {"packets": 0, "duration": 0.0, "size": p.stat().st_size, "file": p.name}
    capinfos = _find_tool("capinfos")
    if capinfos:
        try:
            out = _run_cli([capinfos, "-c", "-u", "-a", "-e", str(p)], timeout=60)
            m = re.search(r"Number of packets:\s*([\d\s]+)", out)
            if m:
                meta["packets"] = int(m.group(1).replace(" ", "") or 0)
            m = re.search(r"Capture duration:\s*([\d.]+)", out)
            if m:
                meta["duration"] = round(float(m.group(1)), 3)
            m = re.search(r"Earliest packet time:\s*(.+)", out)
            if m:
                meta["first"] = m.group(1).strip()[:26]
            m = re.search(r"Latest packet time:\s*(.+)", out)
            if m:
                meta["last"] = m.group(1).strip()[:26]
        except Exception:  # noqa: BLE001
            pass

    phs = _parse_io_phs(_run_tshark(["-r", str(p), "-q", "-z", "io,phs"], timeout=180))
    conv = _parse_conv(
        _run_tshark(["-r", str(p), "-q", "-z", f"conv,{conv_kind}"], timeout=180), conv_kind
    )
    ends = _parse_endpoints(
        _run_tshark(["-r", str(p), "-q", "-z", f"endpoints,{conv_kind}"], timeout=180)
    )
    expert = _parse_expert(_run_tshark(["-r", str(p), "-q", "-z", "expert"], timeout=180))

    if not meta["packets"]:
        meta["packets"] = sum(r["frames"] for r in phs if r["depth"] == 0) or len(phs)

    return {
        "file": meta,
        "protocols": phs[:40],
        "conversations": conv[:30],
        "endpoints": ends[:30],
        "expert": expert[:30],
    }


# ---------------------------------------------------------------- 被动拓扑
def topology_from_pcap(path: str, max_frames: int = 200000) -> dict:
    """从抓包里提取 LLDP / CDP / STP 桥协议单元，推断链路邻居。

    这是**被动**拓扑发现：不登设备，只看线上跑的邻居通告协议。
    """
    p = _resolve(path)
    tshark = _find_tool("tshark")
    if not tshark:
        raise RuntimeError("未找到 tshark")

    links = []
    seen = set()

    # LLDP：拿 本机 MAC → 邻居 chassis/port
    lldp_out = _run_tshark([
        "-r", str(p), "-Y", "lldp", "-T", "fields",
        "-e", "eth.src", "-e", "eth.dst",
        "-e", "lldp.chassis.id", "-e", "lldp.port.id", "-e", "lldp.mgmt_addr",
        "-E", "separator=|", "-c", str(max_frames),
    ], timeout=180)
    for ln in lldp_out.splitlines():
        parts = ln.split("|")
        if len(parts) < 4:
            continue
        src, dst, chassis, port = parts[0], parts[1], parts[2], parts[3]
        mgmt = parts[4] if len(parts) > 4 else ""
        key = (src.lower(), (chassis or dst).lower(), (port or "").lower())
        if key in seen:
            continue
        seen.add(key)
        links.append({
            "local_mac": src,
            "remote_mac": dst if dst != "ff:ff:ff:ff:ff:ff" else "",
            "neighbor": (chassis or dst or "").strip(),
            "remote_if": (port or "").strip(),
            "mgmt_ip": (mgmt or "").strip(),
            "proto": "lldp",
        })

    # CDP
    cdp_out = _run_tshark([
        "-r", str(p), "-Y", "cdp", "-T", "fields",
        "-e", "eth.src", "-e", "cdp.deviceid", "-e", "cdp.portid", "-e", "cdp.address",
        "-E", "separator=|", "-c", str(max_frames),
    ], timeout=180)
    for ln in cdp_out.splitlines():
        parts = ln.split("|")
        if len(parts) < 3:
            continue
        src, dev, port = parts[0], parts[1], parts[2]
        addr = parts[3] if len(parts) > 3 else ""
        key = (src.lower(), (dev or "").lower(), (port or "").lower())
        if key in seen:
            continue
        seen.add(key)
        links.append({
            "local_mac": src,
            "remote_mac": "",
            "neighbor": (dev or "").strip(),
            "remote_if": (port or "").strip(),
            "mgmt_ip": (addr or "").strip(),
            "proto": "cdp",
        })

    # STP 根桥信息
    stp_out = _run_tshark([
        "-r", str(p), "-Y", "stp", "-T", "fields",
        "-e", "eth.src", "-e", "stp.root.bridge", "-e", "stp.root.cost",
        "-E", "separator=|", "-c", "200",
    ], timeout=120)
    roots = []
    for ln in stp_out.splitlines():
        parts = ln.split("|")
        if len(parts) >= 2 and parts[1]:
            roots.append({"bridge_mac": parts[0], "root": parts[1]})

    nodes = [{"id": "__self__", "label": "本机（采集点）", "kind": "self", "ip": "", "vendor": ""}]
    for l in links:
        nid = l["neighbor"] or l["remote_mac"] or "未知邻居"
        if not any(n["id"] == nid for n in nodes):
            nodes.append({
                "id": nid, "label": nid, "kind": "neighbor",
                "ip": l["mgmt_ip"], "vendor": l["proto"].upper(),
            })

    warnings = []
    if not links:
        warnings.append("抓包中未见 LLDP/CDP 通告。被动发现需要镜像/接入承载邻居协议的端口。")

    return {
        "source": "passive-capture",
        "file": p.name,
        "nodes": nodes,
        "links": [
            {
                "from": "__self__",
                "to": l["neighbor"] or l["remote_mac"] or "未知邻居",
                "local_if": l["local_mac"],
                "remote_if": l["remote_if"],
                "proto": l["proto"],
            }
            for l in links
        ],
        "raw_neighbors": links,
        "stp_roots": roots[:10],
        "warnings": warnings,
    }


# ---------------------------------------------------------------- GUI
def open_in_wireshark(path: str) -> dict:
    """用 Wireshark GUI 打开抓包文件（仅本机深挖用）。"""
    p = _resolve(path)
    wireshark = _find_tool("wireshark")
    if not wireshark:
        raise RuntimeError("未找到 Wireshark GUI 可执行文件")
    try:
        subprocess.Popen(
            [wireshark, str(p)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(0x00000008 if os.name == "nt" else 0),
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"启动 Wireshark 失败: {e}") from e
    return {"ok": True, "file": p.name}
