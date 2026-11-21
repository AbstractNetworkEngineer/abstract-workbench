import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Manual
from services.manuals import MANUAL_DIR, SUPPORTED, delete_manual, save_manual_from_path

router = APIRouter(prefix="/api/manuals", tags=["manuals"])


class ManualOut(BaseModel):
    id: int
    filename: str
    kind: str
    chars: int
    created_at: str | None = None

    class Config:
        from_attributes = True


@router.get("")
def list_manuals(db: Session = Depends(get_db)):
    rows = db.query(Manual).order_by(Manual.id.desc()).all()
    return [
        {
            "id": m.id,
            "filename": m.filename,
            "kind": m.kind,
            "chars": m.chars,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]


@router.post("/upload")
async def upload_manual(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """流式导入，不限制单个文档大小与份数。"""
    filename = file.filename or "manual"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(400, f"不支持的格式 {suffix}，请上传 PDF / Word(.docx) / TXT")

    raw_path = MANUAL_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
    try:
        with raw_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):  # 1MB 分块，避免大文件占满内存
                out.write(chunk)
        if raw_path.stat().st_size == 0:
            raise HTTPException(400, "空文件")
        try:
            m = save_manual_from_path(db, filename, raw_path)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"解析失败：{e}") from e
    except HTTPException:
        raw_path.unlink(missing_ok=True)
        raise

    return {
        "id": m.id,
        "filename": m.filename,
        "kind": m.kind,
        "chars": m.chars,
        "message": f"已导入，提取 {m.chars} 字符",
    }


@router.delete("/{manual_id}")
def remove_manual(manual_id: int, db: Session = Depends(get_db)):
    if not delete_manual(db, manual_id):
        raise HTTPException(404, "手册不存在")
    return {"ok": True}
