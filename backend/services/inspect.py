"""智能巡检：多命令采集 + 确定性评分 + AI 分析叙述。

分数由 `inspect_score` 的固定规则算出，同一份配置永远同分；
AI 只负责把发现讲清楚、给整改建议，**不参与打分**（否则两次巡检分数会飘）。
"""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from connectors import ConnectorError, get_dialect
from models import AuditLog, Device
from services.ai import chat_completion
from services.executor import execute_on_device, serial_hint
from services.inspect_score import markdown_report, score_inspect

INSPECT_SYSTEM = (
    "你是资深网络架构师，负责写设备状态检测报告的分析部分。\n"
    "评分已经由规则引擎算出并写在下面，**你不得修改任何数字**。\n"
    "你只输出下面三段，不要输出标题行（## 总评分 / ## 四维评分）：\n"
    "## 主要发现\n"
    "把给定的发现逐条讲清楚：问题是什么、在设备上的证据、会造成什么后果。"
    "按 高/中/低 分组，每条用「【标题】说明」格式，不要编造新问题。\n"
    "## 整改建议\n"
    "按优先级给可执行命令，命令放入一个 ```cli 代码块，每段建议前用一行说明做什么、为什么。\n"
    "## 一句话总评\n"
    "一句话概括设备当前状态。\n"
    "要求：只基于给定的发现与采集内容，不要臆造；语气专业、直接，不要套话。"
)


def collect_commands(device) -> list[str]:
    d = get_dialect(device.vendor)
    brief = "display ip interface brief" if d.name in ("huawei", "h3c") else "show ip interface brief"
    return [d.version_cmd, brief, d.config_cmd]


async def run_inspect(db: Session, device_id: int) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "设备不存在")

    cmds = collect_commands(device)
    try:
        results, via = execute_on_device(device, cmds, timeout_each=25.0)
    except ConnectorError as e:
        raise HTTPException(502, f"连接设备失败：{e}{serial_hint(device)}") from e

    out = {r["command"]: (r.get("output") or "") for r in results}
    version_text = out.get(cmds[0], "")
    interface_text = out.get(cmds[1], "")
    config_text = out.get(cmds[2], "")

    if not any(r["ok"] for r in results):
        raise HTTPException(502, "采集失败：" + (results[0]["output"] if results else "无输出"))

    # 1) 确定性评分：同一份配置永远同一个分
    score = score_inspect(version_text, interface_text, config_text)

    # 2) 把发现交给 AI 写叙述（分数已定死，AI 不得改动）
    findings_md = "\n".join(
        f"- [{f['level']}] -{f['deduct']}分 {f['cat']}｜{f['title']}：{f['detail']}"
        + (f"（证据：{' ; '.join(f['evidence'])}）" if f.get("evidence") else "")
        for f in score["findings"]
    ) or "- （未发现明显问题）"

    facts = "\n\n".join(
        f"$ {r['command']}\n{(r.get('output') or '(无输出)')[:5000]}" for r in results
    )
    user_content = (
        f"设备 {device.name}（{device.vendor}）。\n\n"
        f"【规则引擎已算出的评分（不得改动）】\n"
        f"总评分：{score['total']}/100\n"
        f"四维：安全 {score['dims']['安全']} · 规范 {score['dims']['规范']} · "
        f"容量 {score['dims']['容量']} · 稳定 {score['dims']['稳定']}\n\n"
        f"【已确认的发现（不得新增或删除）】\n{findings_md}\n\n"
        f"【采集原文（节选）】\n{facts}\n\n"
        f"请按格式输出分析部分。"
    )
    analysis = ""
    ai_error = ""
    try:
        analysis = await chat_completion(
            db,
            messages=[{"role": "user", "content": user_content}],
            system=INSPECT_SYSTEM,
            temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001
        # 评分是规则引擎算的，不依赖 AI —— AI 不可用时照样出报告
        ai_error = str(e)[:200]
        analysis = (
            "## 主要发现\n"
            + "\n".join(
                f"- 【{f['level']}】{f['title']}：{f['detail']}" for f in score["findings"]
            or ["- （未发现明显问题）"]
            )
            + "\n\n## 整改建议\n"
            + "\n".join("```cli\n" + "\n".join(f["fix"]) + "\n```" for f in score["findings"] if f.get("fix"))
            + "\n## 一句话总评\n"
            + (f"规则引擎评分 {score['total']}/100。AI 分析暂不可用（{ai_error}），以下发现按固定规则列出。")
        )

    # 3) 分数以规则引擎为准，AI 若擅自改数字也盖不掉
    report = markdown_report(score, analysis)

    db.add(
        AuditLog(
            kind="inspect",
            device_id=device.id,
            device_name=device.name,
            action="设备状态检测",
            detail=json.dumps(
                {
                    "via": via,
                    "cmds": cmds,
                    "total": score["total"],
                    "dims": score["dims"],
                    "findings": [f["id"] for f in score["findings"]],
                },
                ensure_ascii=False,
            ),
            status="ok",
        )
    )
    db.commit()
    return {
        "report": report,
        "via": via,
        "score": score,
        "collected": [{"command": r["command"], "ok": r["ok"]} for r in results],
    }
