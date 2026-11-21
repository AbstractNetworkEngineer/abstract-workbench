"""备份服务：通过连接器拉取设备配置并落盘。"""

import re
from datetime import datetime
from pathlib import Path

from connectors import ConnectorError, connector_from_device, get_dialect
from database import BACKUP_DIR, SessionLocal
from models import AuditLog, Backup, Device


def write_audit(db, kind, action, detail="", status="ok", device=None):
    db.add(
        AuditLog(
            kind=kind,
            device_id=device.id if device else None,
            device_name=device.name if device else "",
            action=action,
            detail=(detail or "")[:4000],
            status=status,
        )
    )
    db.commit()


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", name) or "device"


def run_backup(device_id: int, backup_type: str = "running") -> Backup:
    db = SessionLocal()
    try:
        device = db.get(Device, device_id)
        if device is None:
            raise ConnectorError(f"设备不存在 id={device_id}")
        dialect = get_dialect(device.vendor)
        cmd = dialect.config_cmd if backup_type == "running" else dialect.version_cmd

        try:
            with connector_from_device(device) as conn:
                # 静默初始化：关分页 + 自动 enable
                from services.session_setup import prepare_session

                prepare_session(conn, dialect)
                content = conn.run(cmd, timeout=30)
        except ConnectorError as e:
            backup = Backup(
                device_id=device.id,
                backup_type=backup_type,
                status="failed",
                message=str(e),
            )
            db.add(backup)
            write_audit(db, "backup", f"备份失败: {device.name}", str(e), "failed", device)
            db.commit()
            db.refresh(backup)
            return backup

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        fname = f"{_safe_name(device.name)}_{backup_type}_{stamp}.cfg"
        fpath = BACKUP_DIR / fname
        fpath.write_text(content, encoding="utf-8")

        backup = Backup(
            device_id=device.id,
            backup_type=backup_type,
            file_path=str(fpath),
            size=len(content.encode("utf-8")),
            status="success",
            message=f"获取 {len(content)} 字符配置",
        )
        db.add(backup)
        write_audit(
            db,
            "backup",
            f"备份成功: {device.name}",
            f"type={backup_type}, size={backup.size}B",
            "ok",
            device,
        )
        db.commit()
        db.refresh(backup)

        # 漂移哨兵：与上一份成功备份对比，有变化即留痕
        try:
            prev = (
                db.query(Backup)
                .filter(Backup.device_id == device.id, Backup.status == "success", Backup.id != backup.id)
                .order_by(Backup.id.desc())
                .first()
            )
            if prev and prev.file_path:
                old_text = Path(prev.file_path).read_text(encoding="utf-8", errors="ignore")
                if old_text != content:
                    adds = sum(1 for l in content.splitlines() if l not in old_text.splitlines())
                    dels = sum(1 for l in old_text.splitlines() if l not in content.splitlines())
                    write_audit(
                        db, "drift", f"配置漂移: {device.name}",
                        f"与备份#{prev.id}相比 +{adds}/-{dels} 行（详情见配置漂移页）",
                        "ok", device,
                    )
        except Exception:  # noqa: BLE001
            pass
        return backup
    finally:
        db.close()


def test_connection(payload: dict) -> dict:
    """测试连接（保存设备之前也可调用）。"""
    from connectors import create_connector

    try:
        conn = create_connector(
            protocol=payload.get("protocol", "ssh"),
            host=payload.get("host", ""),
            port=int(payload.get("port") or 22),
            username=payload.get("username", ""),
            password=payload.get("password", ""),
            serial_port=payload.get("serial_port", ""),
            baudrate=int(payload.get("baudrate") or 9600),
            hostname=payload.get("host") or "抽象的工作台-Device",
            encoding=payload.get("encoding", "") or "",
        )
        with conn:
            dialect = get_dialect(payload.get("vendor", "huawei"))
            from services.session_setup import prepare_session

            prepare_session(conn, dialect)
            version = conn.run(dialect.version_cmd, timeout=10)
            return {"ok": True, "message": "连接成功", "version": version[:800]}
    except ConnectorError as e:
        return {"ok": False, "message": str(e), "version": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"连接异常: {e}", "version": ""}
