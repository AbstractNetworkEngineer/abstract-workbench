from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog
from schemas import AuditOut

router = APIRouter(prefix="/api/audits", tags=["audits"])


@router.get("", response_model=list[AuditOut])
def list_audits(kind: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    q = db.query(AuditLog).order_by(AuditLog.id.desc())
    if kind:
        q = q.filter(AuditLog.kind == kind)
    return q.limit(limit).all()
