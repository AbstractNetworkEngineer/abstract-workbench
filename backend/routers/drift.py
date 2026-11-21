from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services import drift as drift_svc

router = APIRouter(prefix="/api/drift", tags=["drift"])


@router.get("")
def summary(db: Session = Depends(get_db)):
    return drift_svc.device_drift_summary(db)


@router.get("/{device_id}/diff")
def diff(device_id: int, db: Session = Depends(get_db)):
    return drift_svc.get_diff(db, device_id)


@router.post("/{device_id}/explain")
async def explain(device_id: int, db: Session = Depends(get_db)):
    return await drift_svc.explain_drift(db, device_id)
