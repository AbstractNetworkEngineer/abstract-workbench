from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

if getattr(sys, "frozen", False):
    # 打包版：数据放在可执行文件旁边，卸载/更新不丢
    DATA_DIR = Path(sys.executable).resolve().parent / "data"
else:
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'netdeck.db'}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns():
    """给已有表补新加的列（create_all 不会为已存在的表补列）。"""
    from sqlalchemy import text

    want = {
        "devices": [("encoding", "VARCHAR(32) DEFAULT ''")],
    }
    with engine.begin() as conn:
        for table, cols in want.items():
            existing = {
                r[1]
                for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if not existing:
                continue
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
