from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Backup, Device
from schemas import BackupCreate, BackupOut
from services.backup_service import run_backup

router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.get("", response_model=list[BackupOut])
def list_backups(device_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Backup).order_by(Backup.id.desc())
    if device_id:
        q = q.filter(Backup.device_id == device_id)
    return q.limit(500).all()


@router.post("", response_model=BackupOut)
def create_backup(data: BackupCreate, db: Session = Depends(get_db)):
    dev = db.get(Device, data.device_id)
    if not dev:
        raise HTTPException(404, "设备不存在")
    # run_backup 使用自己的会话
    return run_backup(data.device_id, data.backup_type)


@router.delete("/{backup_id}")
def delete_backup(backup_id: int, db: Session = Depends(get_db)):
    b = db.get(Backup, backup_id)
    if not b:
        raise HTTPException(404, "备份不存在")
    db.delete(b)
    db.commit()
    return {"ok": True}


@router.get("/{backup_id}/download")
def download_backup(backup_id: int, db: Session = Depends(get_db)):
    b = db.get(Backup, backup_id)
    if not b or not b.file_path:
        raise HTTPException(404, "备份文件不存在")
    import os

    if not os.path.exists(b.file_path):
        raise HTTPException(404, "文件已丢失")
    fname = os.path.basename(b.file_path)
    return FileResponse(b.file_path, filename=fname, media_type="text/plain")
