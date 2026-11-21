from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Device
from schemas import DeviceCreate, DeviceOut, DeviceUpdate, TestConnectionReq
from services.backup_service import test_connection
from services.backup_service import write_audit
from services.security import encrypt_str

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.id.desc()).all()
    for d in devices:
        d.password = ""  # 密文不回传
    return devices


@router.post("", response_model=DeviceOut)
def create_device(data: DeviceCreate, db: Session = Depends(get_db)):
    if db.query(Device).filter(Device.name == data.name).first():
        raise HTTPException(400, "设备名称已存在")
    payload = data.model_dump()
    payload["password"] = encrypt_str(payload.get("password") or "")
    dev = Device(**payload)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    write_audit(db, "system", f"新增设备 {dev.name}", f"{dev.protocol}/{dev.vendor}", "ok", dev)
    dev.password = ""
    return dev


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, data: DeviceUpdate, db: Session = Depends(get_db)):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(404, "设备不存在")
    for k, v in data.model_dump().items():
        if k == "password":
            if not v:
                continue  # 空密码表示不修改
            v = encrypt_str(v)
        setattr(dev, k, v)
    db.commit()
    db.refresh(dev)
    dev.password = ""
    return dev


@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(404, "设备不存在")
    name = dev.name
    db.delete(dev)
    db.commit()
    write_audit(db, "system", f"删除设备 {name}")
    return {"ok": True}


@router.post("/test")
def test(data: TestConnectionReq):
    return test_connection(data.model_dump())
