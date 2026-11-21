"""AI 服务：OpenAI 兼容协议调用（MiMo API / 通义千问兼容端点均可）。"""

import os
from typing import List, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Setting

DEFAULT_SYSTEM = (
    "你是网络运维专家 AI（NetDeck 副驾驶）。你负责分析网络设备配置、生成变更命令、解释故障。"
    "规则：1) 命令必须匹配目标设备厂商方言（华为/H3C 用 display/system-view，"
    "Cisco/DCN 用 show/enable）；2) 输出命令时放入 ```cli 代码块，每行一条命令；"
    "3) 涉及高危操作必须显式标注风险；4) 回答简洁，用中文。"
)


def get_settings(db: Session) -> dict:
    rows = db.query(Setting).all()
    s = {r.key: r.value or "" for r in rows}
    return {
        "ai_base_url": s.get("ai_base_url") or os.getenv("NETDECK_AI_BASE_URL", ""),
        "ai_api_key": s.get("ai_api_key") or os.getenv("NETDECK_AI_API_KEY", ""),
        "ai_model": s.get("ai_model") or os.getenv("NETDECK_AI_MODEL", ""),
        "ai_manual": s.get("ai_manual", ""),
        "env_memory": s.get("env_memory", ""),
        "term_encoding": s.get("term_encoding", "") or os.getenv("NETDECK_TERM_ENCODING", "utf-8"),
    }


def save_settings(db: Session, data: dict) -> None:
    for k, v in data.items():
        row = db.get(Setting, k)
        if row is None:
            row = Setting(key=k, value=v or "")
            db.add(row)
        else:
            row.value = v or ""
    db.commit()


def ai_configured(db: Session) -> bool:
    s = get_settings(db)
    return bool(s["ai_base_url"] and s["ai_api_key"])


def ai_status(db: Session) -> dict:
    """AI 接入状态：逐项检查，明确说清缺什么。

    界面不要笼统显示"未配置" —— 用户配了 API Key 却看到"未配置"会以为软件坏了，
    实际是 Base URL / 模型名没填。把缺失项逐个列出来才好排查。
    """
    s = get_settings(db)
    has_key = bool(s["ai_api_key"])
    has_base = bool(s["ai_base_url"])
    has_model = bool(s["ai_model"])
    missing = []
    if not has_base:
        missing.append("Base URL")
    if not has_key:
        missing.append("API Key")
    if not has_model:
        missing.append("模型名")
    ready = has_base and has_key and has_model
    return {
        "ready": ready,
        "has_base_url": has_base,
        "has_api_key": has_key,
        "has_model": has_model,
        "missing": missing,
        # 给界面直接用的一句话
        "status_text": "已配置" if ready else ("缺 " + "、".join(missing) if missing else "未配置"),
    }


async def chat_completion(
    db: Session,
    messages: List[dict],
    system: Optional[str] = None,
    temperature: float = 0.3,
    timeout: float = 90.0,
) -> str:
    s = get_settings(db)
    base = (s["ai_base_url"] or "").rstrip("/")
    key = s["ai_api_key"]
    model = s["ai_model"] or "mimo-v2.5-pro"
    if not base or not key:
        raise HTTPException(
            status_code=400,
            detail="尚未配置 AI API。请到「设置」页填写 Base URL、API Key 与模型名。",
        )

    sys_msg = {"role": "system", "content": system or DEFAULT_SYSTEM}
    from services.knowledge import full_context

    # 按最后一条用户消息做手册检索，注入补充摘录 + 环境记忆 + 相关段落
    query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            query = (m.get("content") or "")[:300]
            break
    manual_ctx = full_context(db, query)
    if manual_ctx:
        sys_msg["content"] += "\n\n# 知识库\n" + manual_ctx

    payload = {
        "model": model,
        "messages": [sys_msg] + messages,
        "temperature": temperature,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    url = base + ("/chat/completions" if not base.endswith("/chat/completions") else "")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"AI 服务连接失败：{e}") from e

    if resp.status_code != 200:
        body = resp.text[:500]
        raise HTTPException(status_code=502, detail=f"AI 服务返回 {resp.status_code}: {body}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail=f"AI 响应格式异常: {data}") from e


def extract_cli_blocks(text: str) -> List[str]:
    """从 AI 回复中抽取 ```cli / ``` 代码块里的命令行。"""
    commands: List[str] = []
    in_block = False
    lang = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_block:
                in_block = True
                lang = stripped[3:].strip().lower()
            else:
                in_block = False
                lang = ""
            continue
        if in_block and lang in ("", "cli", "shell", "bash", "text"):
            cmd = line.rstrip()
            if cmd.strip() and not cmd.strip().startswith("#"):
                commands.append(cmd)
    return commands


TROUBLE_SYSTEM = (
    "你是资深网络排障专家（会诊模式）。用户给出故障现象，你按步骤排查：\n"
    "1) 每轮先给出简短分析（当前怀疑点）；\n"
    "2) 给出下一步需要执行的 1-3 条排查命令（放入 ```cli 代码块，命令必须匹配设备方言）；\n"
    "3) 如果信息已足够定位根因，给出根因结论与修复命令（```cli）并声明【排障完成】。\n"
    "不要一次抛出全部排查步骤，根据已有输出逐层推进。"
)
