from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import DetectItem
from schemas import DetectItemCreate, DetectItemOut, DetectItemUpdate
from services.detect import (
    catalog,
    ensure_detect_items,
    reset_builtin_items,
    run_detect,
)

router = APIRouter(prefix="/api/detect", tags=["detect"])


class DetectReq(BaseModel):
    device_id: int
    items: list[str] | None = None


@router.get("/catalog")
def get_catalog(db: Session = Depends(get_db)):
    """检测项清单（内置 + 自定义）。"""
    return catalog(db)


@router.get("/items", response_model=list[DetectItemOut])
def list_items(db: Session = Depends(get_db)):
    ensure_detect_items(db)
    return db.query(DetectItem).order_by(DetectItem.sort, DetectItem.id).all()


@router.post("/items", response_model=DetectItemOut)
def create_item(data: DetectItemCreate, db: Session = Depends(get_db)):
    """新增自定义检测项。"""
    if not data.label.strip():
        raise HTTPException(400, "检测项名称不能为空")
    if not (data.cmd_display.strip() or data.cmd_show.strip()):
        raise HTTPException(400, "至少填写一条查看命令")
    base = "".join(ch for ch in data.label.strip().lower() if ch.isalnum()) or "item"
    key = base
    n = 1
    while db.query(DetectItem).filter(DetectItem.key == key).first():
        n += 1
        key = f"{base}_{n}"
    row = DetectItem(
        key=key,
        label=data.label.strip(),
        cat=(data.cat or "自定义").strip(),
        cmd_display=data.cmd_display.strip(),
        cmd_show=data.cmd_show.strip(),
        builtin=False,
        enabled=data.enabled,
        sort=data.sort,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/items/{item_id}", response_model=DetectItemOut)
def update_item(item_id: int, data: DetectItemUpdate, db: Session = Depends(get_db)):
    row = db.get(DetectItem, item_id)
    if row is None:
        raise HTTPException(404, "检测项不存在")
    if not data.label.strip():
        raise HTTPException(400, "检测项名称不能为空")
    if not (data.cmd_display.strip() or data.cmd_show.strip()):
        raise HTTPException(400, "至少填写一条查看命令")
    row.label = data.label.strip()
    row.cat = (data.cat or row.cat or "自定义").strip()
    row.cmd_display = data.cmd_display.strip()
    row.cmd_show = data.cmd_show.strip()
    row.enabled = data.enabled
    row.sort = data.sort
    db.commit()
    db.refresh(row)
    return row


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    row = db.get(DetectItem, item_id)
    if row is None:
        raise HTTPException(404, "检测项不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/items/reset")
def reset_items(db: Session = Depends(get_db)):
    """恢复内置检测项（补齐缺失并还原默认命令）。"""
    added = reset_builtin_items(db)
    return {"ok": True, "restored": added}


@router.post("/run")
def run(req: DetectReq, db: Session = Depends(get_db)):
    """运维检测站：一键采集协议/配置/状态数据（支持自定义检测项）。"""
    return run_detect(db, req.device_id, req.items)
