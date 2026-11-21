"""配置漂移哨兵：对比最近两次备份，AI 解读变更风险。"""

import difflib
import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import AuditLog, Backup, Device
from services.ai import chat_completion

DRIFT_SYSTEM = (
    "你是网络配置变更审计专家。对比同一设备的两份配置（旧→新），输出：\n"
    "## 变更摘要\n一句话说明改了什么\n"
    "## 变更明细\n逐条列出关键差异及含义\n"
    "## 风险评级：高/中/低\n说明理由（安全影响、业务影响、是否合规）\n"
    "## 建议\n是否需要回滚或补救，给出命令（```cli 代码块）\n"
)


def _load_backup_text(b: Backup) -> str:
    try:
        return Path(b.file_path).read_text(encoding="utf-8") if b.file_path else ""
    except OSError:
        return ""


def device_drift_summary(db: Session) -> list[dict]:
    """每台设备最近两次备份的漂移状态。"""
    out = []
    for dev in db.query(Device).all():
        backups = (
            db.query(Backup)
            .filter(Backup.device_id == dev.id, Backup.status == "success")
            .order_by(Backup.id.desc())
            .limit(2)
            .all()
        )
        if len(backups) < 2:
            out.append({"device_id": dev.id, "device_name": dev.name, "state": "nodata",
                        "changed": False, "message": "备份不足 2 份，无法对比"})
            continue
        new, old = backups[0], backups[1]
        tnew, told = _load_backup_text(new), _load_backup_text(old)
        if tnew == told:
            out.append({"device_id": dev.id, "device_name": dev.name, "state": "same",
                        "changed": False, "message": "与上一版一致",
                        "latest_id": new.id, "prev_id": old.id})
        else:
            adds = dels = 0
            for line in difflib.unified_diff(told.splitlines(), tnew.splitlines(), lineterm=""):
                if line.startswith("+") and not line.startswith("+++"):
                    adds += 1
                elif line.startswith("-") and not line.startswith("---"):
                    dels += 1
            out.append({
                "device_id": dev.id, "device_name": dev.name, "state": "changed",
                "changed": True, "message": f"+{adds} / -{dels} 行",
                "latest_id": new.id, "prev_id": old.id,
            })
    return out


def get_diff(db: Session, device_id: int) -> dict:
    dev = db.get(Device, device_id)
    if dev is None:
        raise HTTPException(404, "设备不存在")
    backups = (
        db.query(Backup)
        .filter(Backup.device_id == device_id, Backup.status == "success")
        .order_by(Backup.id.desc())
        .limit(2)
        .all()
    )
    if len(backups) < 2:
        raise HTTPException(400, "备份不足 2 份，无法对比")
    new, old = backups[0], backups[1]
    diff = "\n".join(
        difflib.unified_diff(
            _load_backup_text(old).splitlines(),
            _load_backup_text(new).splitlines(),
            fromfile=f"备份#{old.id}",
            tofile=f"备份#{new.id}",
            lineterm="",
        )
    )
    return {"device_id": device_id, "device_name": dev.name, "diff": diff or "(无差异)"}


async def explain_drift(db: Session, device_id: int) -> dict:
    d = get_diff(db, device_id)
    reply = await chat_completion(
        db,
        messages=[{"role": "user", "content": f"设备 {d['device_name']} 配置差异（旧→新）：\n{d['diff'][:8000]}"}],
        system=DRIFT_SYSTEM,
        temperature=0.2,
    )
    db.add(
        AuditLog(kind="drift", device_id=device_id, device_name=d["device_name"],
                 action="AI 漂移解读", detail=reply[:200], status="ok")
    )
    db.commit()
    return {"report": reply, "diff": d["diff"]}
