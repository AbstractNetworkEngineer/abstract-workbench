"""设备 CLI 级错误识别。

传输层 `conn.run()` 成功只代表"有回显"，不代表设备接受了这条命令。
网络设备会用一行错误文案拒绝非法命令（例如 `% Invalid input detected at '^' marker.`），
若不识别它，就会把"设备拒绝"误判成"执行成功"。
"""

import re

# 各厂商 CLI 拒绝命令的典型签名（大小写不敏感）
_CLI_ERROR_RES: list[tuple[str, re.Pattern]] = [
    ("设备拒绝：无法识别的命令", re.compile(r"(?:^|\n)\s*%\s*Unrecognized\s+command", re.I)),
    ("设备拒绝：命令输入无效", re.compile(r"Invalid\s+input\s+detected", re.I)),
    ("设备拒绝：命令不完整", re.compile(r"(?:^|\n)\s*%\s*Incomplete\s+command", re.I)),
    ("设备拒绝：命令有歧义", re.compile(r"(?:^|\n)\s*%\s*Ambiguous\s+command", re.I)),
    ("设备拒绝：参数错误", re.compile(r"(?:^|\n)\s*%\s*Wrong\s+parameter", re.I)),
    ("设备拒绝：未知命令", re.compile(r"(?:^|\n)\s*(?:%\s*)?Unknown\s+command", re.I)),
    ("设备拒绝：非法命令", re.compile(r"(?:^|\n)\s*(?:%\s*)?Invalid\s+command", re.I)),
    ("设备拒绝：不支持的命令", re.compile(r"Command\s+(?:is\s+)?not\s+supported|not\s+a\s+valid\s+command", re.I)),
    ("设备拒绝：未识别的命令", re.compile(r"Error:\s*Unrecognized\s+command", re.I)),
    ("设备拒绝：参数错误", re.compile(r"Error:\s*Wrong\s+parameter", re.I)),
    ("设备拒绝：命令被拒绝", re.compile(r"Command\s+rejected|rejected\s+by\s+the\s+device", re.I)),
    ("设备拒绝：权限不足", re.compile(r"(?:Permission|Access)\s+denied", re.I)),
    ("设备拒绝：缺少参数", re.compile(r"(?:^|\n)\s*%\s*Missing\s+parameter", re.I)),
]


def detect_cli_error(output: str) -> str | None:
    """若设备回显表示命令被拒绝，返回可读原因；正常返回 None。"""
    if not output or not output.strip():
        return None
    text = output.replace("\r", "")
    for label, pat in _CLI_ERROR_RES:
        if pat.search(text):
            return label
    # 裸 `^` 标记行：Cisco/DCN/华为 定位非法字符的标准写法
    if re.search(r"(?:^|\n)\s*\^\s*(?:\n|$)", text):
        return "设备拒绝：命令不被接受（^ 标记定位出错位置）"
    return None


def judge_command(command: str, output: str) -> dict:
    """把一次命令执行的结果判定为 {command, output, ok, error?}。

    ok=True 表示设备接受了这条命令；设备回显错误文案时必须为 False。
    """
    err = detect_cli_error(output)
    item = {"command": command, "output": output or "", "ok": err is None}
    if err:
        item["error"] = err
    return item
