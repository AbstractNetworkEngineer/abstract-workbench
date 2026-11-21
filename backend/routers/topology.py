from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from connectors import ConnectorError
from database import get_db
from models import Device
from services.topology import collect_topology

router = APIRouter(prefix="/api/topology", tags=["topology"])


class TopologyReq(BaseModel):
    device_id: int


@router.post("/discover")
def discover(req: TopologyReq, db: Session = Depends(get_db)):
    """从 LLDP/CDP/ARP 发现设备邻居，返回可直接画拓扑的 nodes/links。"""
    device = db.get(Device, req.device_id)
    if device is None:
        raise HTTPException(404, "设备不存在")
    try:
        return collect_topology(device)
    except ConnectorError as e:
        raise HTTPException(502, str(e)) from e
