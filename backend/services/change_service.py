"""配置写入服务：AI 生成命令 → 人工确认 → SSH 执行 → 审计留痕。"""

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from connectors import ConnectorError, connector_from_device, get_dialect
from models import AuditLog, Device
from services.ai import chat_completion, extract_cli_blocks

PLAN_SYSTEM = (
    "你是网络设备变更工程师。根据用户意图，为目标设备生成可直接执行的 CLI 命令序列。\n"
    "要求：\n"
    "1) 严格匹配设备厂商方言与型号；命令必须是该型号确实支持的写法，禁止臆造命令。\n"
    "2) 优先依据「知识库」里提供的操作手册段落来写命令；只有在手册段落里能确认存在的命令，才允许放进 ```cli 代码块。\n"
    "3) 若某个功能在手册段落里找不到对应命令，不要猜命令名，改为在正文写明"
    "「⚠️ 手册中未找到 X 的命令，请在设备 `configure terminal` 下用 `?` 现场确认关键字」，"
    "并把这一步做成一条可执行的查证命令（如在对应视图下敲 `?`）放进代码块。\n"
    "4) 命令放入一个 ```cli 代码块，每行一条，顺序即执行顺序；不要把解释性注释写进代码块。\n"
    "5) 代码块外用 3-5 句话说明变更内容与风险等级（低/中/高），并明确指出哪些命令是手册已确认的、哪些仍需现场查证。\n"
    "6) 若意图不明确或高危，先在正文说明，不要急着给命令。\n"
    "7) 进入配置视图前先确认当前模式：若设备提示符已经是 `(config)#`，就不要再敲 `configure terminal`，"
    "否则设备会报 % Invalid input。用 `exit` 退到特权模式再 `write` 保存。"
)


async def preview_change(db: Session, device_id: int, intent: str, context: str = "") -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "设备不存在")
    dialect = get_dialect(device.vendor)

    model_hint = f"，型号/备注：{device.notes}" if device.notes else ""
    user_content = (
        f"目标设备：{device.name}（厂商：{dialect.label}，协议：{device.protocol}{model_hint}）\n"
        f"方言要点：配置命令用 `{dialect.config_cmd}`，进入配置视图用 `{dialect.view_enter}`，"
        f"保存用 `{dialect.save_cmd}`，提示符形如 {dialect.prompt_hint}\n"
        f"\n用户意图：{intent}\n"
    )
    if context:
        user_content += f"\n当前配置/现场信息：\n{context[:4000]}\n"
    user_content += "\n请生成变更命令。"

    reply = await chat_completion(
        db,
        messages=[{"role": "user", "content": user_content}],
        system=PLAN_SYSTEM,
        temperature=0.2,
    )
    commands = extract_cli_blocks(reply)
    risk = "中"
    for level in ("高", "中", "低"):
        if level in reply:
            risk = level
            break

    # 命令对照手册查证：让"设备是否真支持"可人工核实，而不是听 AI 一面之词
    from services.knowledge import verify_commands

    command_checks = verify_commands(db, commands)

    # 预检：AI 自审命令与现场信息的冲突/遗漏
    precheck = ""
    if commands:
        unverified = [c["command"] for c in command_checks if c["status"] == "unverified"]
        check_note = ""
        if unverified:
            check_note = (
                "\n\n【手册核验警告】以下命令在设备操作手册中查无出处，可能是臆造或该型号不支持，"
                "请重点审核并在结论中标注：\n" + "\n".join(f"  - {c}" for c in unverified)
            )
        try:
            precheck = await chat_completion(
                db,
                messages=[{
                    "role": "user",
                    "content": (
                        f"请预检以下即将写入 {device.name}（{dialect.label}）的命令，"
                        f"指出冲突、遗漏、不可逆风险，最后给结论一行：【预检通过】或【需要修改】：\n"
                        + "\n".join(commands)
                        + check_note
                        + ("\n\n现场信息：\n" + context[:3000] if context else "")
                    ),
                }],
                system="你是变更预检审核员，只做审核不生成新方案，回答简洁。"
                       "若发现手册中不存在的命令，必须在结论前明确点名并判为【需要修改】。",
                temperature=0.1,
            )
        except Exception:  # noqa: BLE001
            precheck = ""

    db.add(
        AuditLog(
            kind="ai",
            device_id=device.id,
            device_name=device.name,
            action="生成配置写入方案",
            detail=f"intent={intent[:200]}, cmds={len(commands)}, "
                   f"unverified={sum(1 for c in command_checks if c['status'] == 'unverified')}",
            status="pending",
        )
    )
    db.commit()

    return {
        "device": {"id": device.id, "name": device.name, "vendor": dialect.label},
        "commands": commands,
        "command_checks": command_checks,
        "risk": risk,
        "analysis": reply,
        "precheck": precheck,
    }


async def execute_change(db: Session, device_id: int, commands: list[str], note: str = "", intent: str = "") -> dict:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "设备不存在")
    if not commands:
        raise HTTPException(400, "没有可执行的命令")

    from services.executor import execute_on_device, serial_hint

    try:
        results, via = execute_on_device(device, commands)
    except ConnectorError as e:
        hint = str(e) + serial_hint(device)
        db.add(
            AuditLog(
                kind="change",
                device_id=device.id,
                device_name=device.name,
                action="配置写入失败（连接）",
                detail=hint,
                status="failed",
            )
        )
        db.commit()
        raise HTTPException(502, f"连接设备失败：{hint}") from e

    status = "ok" if all(r["ok"] for r in results) else "failed"

    # 后检：把执行输出（含每条命令的设备判定）交给 AI 判断意图是否达成
    postcheck = ""
    if intent.strip() and results:
        outputs = "\n\n".join(
            f"$ {r['command']}\n[设备判定: {'接受' if r['ok'] else '拒绝 - ' + r.get('error', '未知')}]"
            f"\n{(r['output'] or '(无输出)')[:1500]}"
            for r in results
        )
        try:
            postcheck = await chat_completion(
                db,
                messages=[{
                    "role": "user",
                    "content": (
                        f"变更意图：{intent}\n执行命令、设备判定与输出：\n{outputs[:6000]}\n"
                        f"请判断意图是否达成，结尾给一行结论：【达成】/【部分达成】/【未达成】。"
                    ),
                }],
                system=(
                    "你是变更后检员，简短评估，不要生成新命令。"
                    "判断必须以设备真实回显为准，不得粉饰结果：\n"
                    "只要有任何一条命令被设备判定为「拒绝」（例如 % Invalid input、Unknown command），"
                    "该部分就一律算未达成，必须在结论里点名是哪条命令被拒绝、设备给出的错误原因，"
                    "并明确说「设备不支持该命令，本次写入未生效」。"
                    "禁止在设备报错的情况下声称配置成功或意图达成。"
                ),
                temperature=0.1,
            )
        except Exception:  # noqa: BLE001
            postcheck = ""

    failed = [r["command"] for r in results if not r["ok"]]
    detail = json.dumps(
        {
            "note": note,
            "commands": [r["command"] for r in results],
            "failed": failed,
            "fail_reasons": {r["command"]: r.get("error", "") for r in results if not r["ok"]},
            "status": status,
            "via": via,
        },
        ensure_ascii=False,
    )
    db.add(
        AuditLog(
            kind="change",
            device_id=device.id,
            device_name=device.name,
            action=(
                "配置写入成功" if status == "ok"
                else f"配置写入失败（{len(failed)}/{len(results)} 条被设备拒绝）"
            ) + ("（活动会话）" if via == "live-session" else ""),
            detail=detail,
            status=status,
        )
    )
    db.commit()
    return {"status": status, "results": results, "via": via, "postcheck": postcheck}
