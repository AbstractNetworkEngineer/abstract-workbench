"""定时备份策略调度器：每 30 秒检查一次到期任务。"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from database import SessionLocal
from models import Strategy
from services.backup_service import run_backup

logger = logging.getLogger("netdeck.scheduler")


async def _tick():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        strategies = db.query(Strategy).filter(Strategy.enabled.is_(True)).all()
        for st in strategies:
            due = st.next_run is None or st.next_run <= now
            if not due:
                continue
            try:
                ids = json.loads(st.device_ids or "[]")
            except json.JSONDecodeError:
                ids = []
            for did in ids:
                try:
                    await asyncio.to_thread(run_backup, did, st.backup_type)
                except Exception as e:  # noqa: BLE001
                    logger.warning("strategy %s device %s backup failed: %s", st.id, did, e)
            st.last_run = now
            st.next_run = now + timedelta(hours=max(1, st.interval_hours or 24))
            db.commit()
    finally:
        db.close()


async def scheduler_loop():
    logger.info("NetDeck scheduler started")
    while True:
        try:
            await _tick()
        except Exception as e:  # noqa: BLE001
            logger.exception("scheduler tick failed: %s", e)
        await asyncio.sleep(30)
