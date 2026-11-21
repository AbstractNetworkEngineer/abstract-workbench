from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog, Backup, Device, Strategy
from services.ai import ai_status

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats(db: Session = Depends(get_db)):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    audits = (
        db.query(AuditLog).order_by(AuditLog.id.desc()).limit(8).all()
    )
    st = ai_status(db)
    # Wireshark 抓包接入：工具就绪状态 + 抓包文件概况
    try:
        from services import capture as cap

        cap_st = cap.wireshark_status()
        cap_files = cap.list_captures()
        capture = {
            "ready": cap_st["ready"],
            "version": cap_st.get("version", ""),
            "files": len(cap_files),
            "latest": cap_files[0]["filename"] if cap_files else "",
        }
    except Exception:  # noqa: BLE001
        capture = {"ready": False, "version": "", "files": 0, "latest": ""}
    return {
        "devices": db.query(Device).count(),
        "backups": db.query(Backup).count(),
        "backups_today": db.query(Backup).filter(Backup.created_at >= today_start).count(),
        "strategies": db.query(Strategy).filter(Strategy.enabled.is_(True)).count(),
        "audits": db.query(AuditLog).count(),
        "ai_configured": st["ready"],
        # 逐项状态：没配好时界面要能说清缺哪一项，而不是笼统"未配置"
        "ai_status": st,
        "capture": capture,
        "recent_audits": [
            {
                "id": a.id,
                "kind": a.kind,
                "action": a.action,
                "device_name": a.device_name,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in audits
        ],
    }
