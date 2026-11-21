from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import ChangeExecuteReq, ChangePreviewReq
from services.change_service import execute_change, preview_change

router = APIRouter(prefix="/api/changes", tags=["changes"])


@router.post("/preview")
async def preview(data: ChangePreviewReq, db: Session = Depends(get_db)):
    """AI 生成变更方案（不落设备，仅预览）。"""
    return await preview_change(db, data.device_id, data.intent, data.context)


@router.post("/execute")
async def execute(data: ChangeExecuteReq, db: Session = Depends(get_db)):
    """人工确认后的命令执行（闸门出口）+ AI 后检。"""
    return await execute_change(db, data.device_id, data.commands, data.note, data.intent)
