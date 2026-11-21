from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.inspect import run_inspect

router = APIRouter(prefix="/api/inspect", tags=["inspect"])


class InspectReq(BaseModel):
    device_id: int


@router.post("")
async def inspect(req: InspectReq, db: Session = Depends(get_db)):
    """智能巡检：采集设备信息 → AI 打分体检报告。"""
    return await run_inspect(db, req.device_id)
