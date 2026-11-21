from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Device, Setting
from schemas import ChatReq
from services.ai import TROUBLE_SYSTEM, chat_completion, extract_cli_blocks, get_settings
from services.backup_service import write_audit

router = APIRouter(prefix="/api/ai", tags=["ai"])


class TroubleReq(BaseModel):
    device_id: int | None = None
    symptom: str
    history: str = ""   # 已执行命令与输出
    rounds: int = 0


@router.get("/config")
def ai_config(db: Session = Depends(get_db)):
    s = get_settings(db)
    from services.ai import ai_status

    st = ai_status(db)
    # API Key 不回传明文，只回传是否已配置
    return {
        "ai_base_url": s["ai_base_url"],
        "ai_model": s["ai_model"],
        "ai_manual_len": len(s["ai_manual"]),
        "key_set": bool(s["ai_api_key"]),
        # 逐项状态：ready / missing / status_text，界面据此显示"缺哪一项"
        "ready": st["ready"],
        "missing": st["missing"],
        "status_text": st["status_text"],
        "has_base_url": st["has_base_url"],
        "has_api_key": st["has_api_key"],
        "has_model": st["has_model"],
    }


@router.post("/chat")
async def chat(data: ChatReq, db: Session = Depends(get_db)):
    messages = []
    if data.context:
        messages.append({"role": "system", "content": f"现场上下文：\n{data.context[:6000]}"})
    messages += data.messages
    if not messages:
        raise HTTPException(400, "消息不能为空")
    reply = await chat_completion(db, messages)
    write_audit(db, "ai", f"AI 对话 ({data.mode})", data.messages[-1].get("content", "")[:200])
    return {"reply": reply}


@router.post("/analyze")
async def analyze(data: ChatReq, db: Session = Depends(get_db)):
    """多维度配置分析入口。"""
    config_text = data.context
    if not config_text:
        raise HTTPException(400, "缺少配置文本（context）")
    prompt = (
        "请对以下网络设备配置做多维度分析，输出：\n"
        "1) 安全风险（明文口令、不安全协议、权限过大等）\n"
        "2) 配置规范问题（命名、冗余、缺失项）\n"
        "3) 优化建议（按优先级排序，给出具体命令）\n"
        "4) 一句话总评\n\n配置：\n" + config_text[:8000]
    )
    reply = await chat_completion(
        db,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    write_audit(db, "ai", "AI 配置分析", f"len={len(config_text)}")
    return {"reply": reply}


@router.post("/troubleshoot")
async def troubleshoot(req: TroubleReq, db: Session = Depends(get_db)):
    """排障向导：现象 + 已有排查输出 → 怀疑点 + 下一步排查命令。"""
    if not req.symptom.strip():
        raise HTTPException(400, "请描述故障现象")
    dev_name = "未知设备"
    if req.device_id:
        dev = db.get(Device, req.device_id)
        if dev:
            dev_name = f"{dev.name}（{dev.vendor}）"
    prompt = (
        f"设备：{dev_name}\n故障现象：{req.symptom}\n"
        f"已进行的排查（命令与输出）：\n{req.history or '（尚无）'}\n"
        f"当前轮次：{req.rounds + 1}\n请给出本轮分析与下一步排查命令。"
    )
    reply = await chat_completion(
        db,
        messages=[{"role": "user", "content": prompt}],
        system=TROUBLE_SYSTEM,
        temperature=0.2,
    )
    commands = extract_cli_blocks(reply)
    write_audit(db, "ai", f"排障向导 第{req.rounds + 1}轮", req.symptom[:120])
    return {"reply": reply, "commands": commands, "done": "【排障完成】" in reply}
