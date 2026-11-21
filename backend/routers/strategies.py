import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Strategy
from schemas import StrategyCreate, StrategyOut
from services.backup_service import write_audit

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyOut])
def list_strategies(db: Session = Depends(get_db)):
    return db.query(Strategy).order_by(Strategy.id.desc()).all()


@router.post("", response_model=StrategyOut)
def create_strategy(data: StrategyCreate, db: Session = Depends(get_db)):
    st = Strategy(
        name=data.name,
        device_ids=json.dumps(data.device_ids, ensure_ascii=False),
        backup_type=data.backup_type,
        interval_hours=data.interval_hours,
        enabled=data.enabled,
        next_run=datetime.utcnow() + timedelta(hours=data.interval_hours),
    )
    db.add(st)
    db.commit()
    db.refresh(st)
    write_audit(db, "system", f"创建策略 {st.name}", f"每 {st.interval_hours}h")
    return st


@router.put("/{sid}", response_model=StrategyOut)
def update_strategy(sid: int, data: StrategyCreate, db: Session = Depends(get_db)):
    st = db.get(Strategy, sid)
    if not st:
        raise HTTPException(404, "策略不存在")
    st.name = data.name
    st.device_ids = json.dumps(data.device_ids, ensure_ascii=False)
    st.backup_type = data.backup_type
    st.interval_hours = data.interval_hours
    st.enabled = data.enabled
    db.commit()
    db.refresh(st)
    return st


@router.delete("/{sid}")
def delete_strategy(sid: int, db: Session = Depends(get_db)):
    st = db.get(Strategy, sid)
    if not st:
        raise HTTPException(404, "策略不存在")
    db.delete(st)
    db.commit()
    return {"ok": True}
