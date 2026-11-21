"""会话初始化：静默完成特权模式进入与分页关闭，不打扰用户终端。"""

import logging

logger = logging.getLogger("netdeck.session")


def prepare_session(connector, dialect) -> str:
    """连接建立后的准备工作。全部静默执行（错误不回显到终端）。

    顺序很关键：必须先 enable 进特权模式，再关分页 ——
    Cisco/DCN 系的 `terminal length 0` 只有特权模式才认，先关分页会
    "% Invalid input" 并留下 --More-- 翻页问题。
    """
    enable_cmd = getattr(dialect, "enable_cmd", "") or ""
    if enable_cmd:
        try:
            out = connector.run(enable_cmd, timeout=8)
            if out and ("denied" in out.lower() or "invalid" in out.lower()):
                logger.info("enable not accepted: %s", out[:120])
        except Exception as e:  # noqa: BLE001
            logger.debug("enable failed: %s", e)

    for pc in getattr(dialect, "paging_cmds", []) or []:
        try:
            connector.run(pc, timeout=6)
        except Exception as e:  # noqa: BLE001
            logger.debug("paging cmd %r failed: %s", pc, e)

    return "ready"
