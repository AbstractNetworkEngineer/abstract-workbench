from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import SettingsOut, SettingsUpdate
from services.ai import get_settings, save_settings
from services.encoding import ENCODINGS, normalize, set_default

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/encodings")
def list_encodings():
    """终端可用字符编码（Python 内置 codec，无需额外下载）。"""
    return ENCODINGS


def _out(s: dict) -> SettingsOut:
    return SettingsOut(
        ai_base_url=s.get("ai_base_url", ""),
        ai_api_key="",  # 不回传
        ai_model=s.get("ai_model", ""),
        ai_manual=s.get("ai_manual", ""),
        env_memory=s.get("env_memory", ""),
        term_encoding=s.get("term_encoding", "") or "utf-8",
    )


@router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    return _out(get_settings(db))


@router.put("", response_model=SettingsOut)
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    """**部分更新**：只写请求体里出现过的字段。

    之前是全量覆盖，导致只提交 term_encoding 的调用会把 AI Base URL / 模型 /
    手册摘录 / 环境记忆一并清空。用 exclude_unset 保证"没传的字段不动"。
    """
    provided = data.model_dump(exclude_unset=True)
    payload: dict = {}
    for key in ("ai_base_url", "ai_model", "ai_manual", "env_memory"):
        if key in provided:
            payload[key] = provided[key] or ""
    if "term_encoding" in provided:
        payload["term_encoding"] = normalize(provided.get("term_encoding") or "utf-8")
    # 空 key 表示不修改，避免覆盖已有密钥
    if provided.get("ai_api_key"):
        payload["ai_api_key"] = provided["ai_api_key"]

    if payload:
        save_settings(db, payload)
        if "term_encoding" in payload:
            set_default(payload["term_encoding"])
    return _out(get_settings(db))
