from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ---------- devices ----------
class DeviceBase(BaseModel):
    name: str
    vendor: str = "huawei"
    protocol: str = "ssh"
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    serial_port: str = ""
    baudrate: int = 9600
    encoding: str = ""
    notes: str = ""


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(DeviceBase):
    pass


class DeviceOut(DeviceBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TestConnectionReq(BaseModel):
    """Ad-hoc connection test (before saving a device)."""

    protocol: str = "ssh"
    vendor: str = "huawei"
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    serial_port: str = ""
    baudrate: int = 9600
    encoding: str = ""


# ---------- backups ----------
class BackupOut(BaseModel):
    id: int
    device_id: int
    backup_type: str
    size: int
    status: str
    message: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BackupCreate(BaseModel):
    device_id: int
    backup_type: str = "running"


# ---------- strategies ----------
class StrategyCreate(BaseModel):
    name: str
    device_ids: List[int] = []
    backup_type: str = "running"
    interval_hours: int = 24
    enabled: bool = True


class StrategyOut(BaseModel):
    id: int
    name: str
    device_ids: str
    backup_type: str
    interval_hours: int
    enabled: bool
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- audit ----------
class AuditOut(BaseModel):
    id: int
    kind: str
    device_id: Optional[int] = None
    device_name: str
    action: str
    detail: str
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- settings ----------
class SettingsOut(BaseModel):
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_manual: str = ""
    env_memory: str = ""
    term_encoding: str = ""


class SettingsUpdate(BaseModel):
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_manual: str = ""
    env_memory: str = ""
    term_encoding: str = ""


# ---------- AI ----------
class ChatReq(BaseModel):
    messages: List[dict] = Field(default_factory=list)
    context: str = ""
    mode: str = "chat"  # chat / analyze / plan


class ChangePreviewReq(BaseModel):
    device_id: int
    intent: str
    context: str = ""


class ChangeExecuteReq(BaseModel):
    device_id: int
    commands: List[str]
    note: str = ""
    intent: str = ""


# ---------- stats ----------
class StatsOut(BaseModel):
    devices: int
    backups: int
    backups_today: int
    strategies: int
    audits: int
    ai_configured: bool
    recent_audits: List[Any] = []


# ---------- detect items（可自定义的检测项） ----------
class DetectItemBase(BaseModel):
    label: str
    cat: str = "自定义"
    cmd_display: str = ""  # 华为 / H3C 命令
    cmd_show: str = ""  # DCN / Cisco / 通用 命令
    enabled: bool = True
    sort: int = 100


class DetectItemCreate(DetectItemBase):
    pass


class DetectItemUpdate(DetectItemBase):
    pass


class DetectItemOut(DetectItemBase):
    id: int
    key: str
    builtin: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
