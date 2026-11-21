from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog
from services import capture as cap

router = APIRouter(prefix="/api/capture", tags=["capture"])


class StartReq(BaseModel):
    iface: str
    bpf_filter: str = ""
    max_packets: int = 20000
    duration: int = 60
    name: str = ""


class SidReq(BaseModel):
    id: str


class PathReq(BaseModel):
    path: str
    kind: str = "ip"


@router.get("/status")
def ws_status():
    """Wireshark 接入自检（工具链 / 版本 / 抓包目录）。"""
    return cap.wireshark_status()


@router.get("/interfaces")
def interfaces():
    return {"interfaces": cap.list_interfaces()}


@router.post("/start")
def start(req: StartReq, db: Session = Depends(get_db)):
    try:
        s = cap.start_capture(
            req.iface, req.bpf_filter, req.max_packets, req.duration, req.name
        )
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    db.add(AuditLog(kind="capture", action="开始抓包",
                    detail=f"iface={req.iface} filter={req.bpf_filter!r} file={s['filename']}",
                    status="ok"))
    db.commit()
    return s


@router.post("/stop")
def stop(req: SidReq, db: Session = Depends(get_db)):
    try:
        s = cap.stop_capture(req.id)
    except RuntimeError as e:
        raise HTTPException(404, str(e)) from e
    db.add(AuditLog(kind="capture", action="停止抓包",
                    detail=f"file={s.get('filename')} size={s.get('file_size')}",
                    status="ok"))
    db.commit()
    return s


@router.get("/sessions")
def sessions():
    return {"sessions": cap.list_sessions()}


@router.get("/files")
def files():
    return {"files": cap.list_captures()}


@router.post("/analyze")
def analyze(req: PathReq):
    try:
        return cap.analyze_pcap(req.path, req.kind)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/topology")
def topology(req: PathReq):
    """被动拓扑发现：从抓包里的 LLDP/CDP 通告推断邻居。"""
    try:
        return cap.topology_from_pcap(req.path)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/findings")
def findings(req: PathReq):
    """包级运行状态发现：广播风暴 / ARP 泛洪 / 明文协议 / 协议异常。

    这是 Wireshark 能力嵌入巡检与检测站的接口 —— 不跳页，直接给结论。
    """
    try:
        from services.capture_findings import packet_findings

        return packet_findings(req.path)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/open")
def open_gui(req: PathReq, db: Session = Depends(get_db)):
    """用 Wireshark GUI 打开（本机深挖用）。"""
    try:
        r = cap.open_in_wireshark(req.path)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    db.add(AuditLog(kind="capture", action="打开 Wireshark", detail=r.get("file", ""), status="ok"))
    db.commit()
    return r
