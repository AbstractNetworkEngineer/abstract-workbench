from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False)
    vendor = Column(String(32), default="huawei")  # huawei / h3c / dcn / cisco / generic
    protocol = Column(String(16), default="ssh")  # ssh / telnet / serial / mock / outband
    host = Column(String(128), default="")
    port = Column(Integer, default=22)
    username = Column(String(64), default="")
    password = Column(String(128), default="")
    serial_port = Column(String(32), default="")
    baudrate = Column(Integer, default=9600)
    encoding = Column(String(32), default="")  # 终端字符编码，空=用全局默认（GBK/GB18030 等）
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    backups = relationship("Backup", back_populates="device", cascade="all, delete-orphan")


class Backup(Base):
    __tablename__ = "backups"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    backup_type = Column(String(32), default="running")  # running / startup / all
    file_path = Column(String(512), default="")
    size = Column(Integer, default=0)
    status = Column(String(16), default="success")  # success / failed
    message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device", back_populates="backups")


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    device_ids = Column(Text, default="[]")  # JSON list of device ids
    backup_type = Column(String(32), default="running")
    interval_hours = Column(Integer, default=24)
    enabled = Column(Boolean, default=True)
    next_run = Column(DateTime, nullable=True)
    last_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(24), default="system")  # backup / change / ai / system / connection
    device_id = Column(Integer, nullable=True)
    device_name = Column(String(64), default="")
    action = Column(String(128), default="")
    detail = Column(Text, default="")
    status = Column(String(16), default="ok")  # ok / failed / pending
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")


class Manual(Base):
    """导入的设备操作手册（已提取纯文本）。"""

    __tablename__ = "manuals"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(256), nullable=False)
    kind = Column(String(16), default="txt")  # txt / pdf / docx
    chars = Column(Integer, default=0)
    file_path = Column(String(512), default="")  # 原始文件
    text_path = Column(String(512), default="")  # 提取的纯文本
    created_at = Column(DateTime, default=datetime.utcnow)


class DetectItem(Base):
    """运维检测站的检测项：内置项与用户自定义项同一张表。

    每项 = 一个展示名 + 一条查看命令（按厂商方言分成两列），用户可自行增删改、
    停用、排序，不必被写死的协议清单绑住。
    """

    __tablename__ = "detect_items"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, nullable=False)  # 唯一标识
    label = Column(String(64), nullable=False)  # 展示名，如 "设备版本"
    cat = Column(String(32), default="自定义")  # 分组，如 基础信息 / 接口 / 自定义
    cmd_display = Column(String(256), default="")  # 华为 / H3C 方言命令
    cmd_show = Column(String(256), default="")  # DCN / Cisco / 通用 方言命令
    builtin = Column(Boolean, default=False)  # 是否内置项
    enabled = Column(Boolean, default=True)
    sort = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.utcnow)
