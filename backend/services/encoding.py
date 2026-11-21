"""终端字符编码：编码表 + 安全解码/编码。

网络设备回显的字节不一定 UTF-8 —— 国产设备（华为/H3C/神州数码）常见 GBK / GB2312 /
GB18030，老 Cisco 控制台是 CP437/CP850，日韩设备 Shift-JIS / EUC-KR。
解码错了就满屏乱码，所以终端必须能切换编码。

编码器（codec）Python 内置全带，不需要额外下载字体包；但渲染端要有中文字形，
前端字体栈会带上 Microsoft YaHei / SimHei / NSimSun。
"""

import codecs

# 展示名对齐 SecureCRT 的叫法，用户看起来眼熟
ENCODINGS: list[dict[str, str]] = [
    {"value": "utf-8", "label": "UTF-8（默认）"},
    {"value": "gbk", "label": "ANSI/OEM 简体中文 GBK"},
    {"value": "gb2312", "label": "简体中文 GB2312"},
    {"value": "gb18030", "label": "GB18030 简体中文"},
    {"value": "hz", "label": "HZ-GB2312 简体中文"},
    {"value": "big5", "label": "繁体中文 Big5"},
    {"value": "big5hkscs", "label": "繁体中文 Big5-HKSCS"},
    {"value": "shift_jis", "label": "日文 Shift-JIS"},
    {"value": "euc_jp", "label": "日文 EUC-JP"},
    {"value": "euc_kr", "label": "韩文 EUC-KR"},
    {"value": "cp437", "label": "OEM 美国 (CP437)"},
    {"value": "cp850", "label": "OEM 多语言拉丁-1 (CP850)"},
    {"value": "iso8859-1", "label": "西欧 ISO-8859-1"},
    {"value": "iso8859-15", "label": "西欧 ISO-8859-15"},
    {"value": "cp1252", "label": "西欧 Windows-1252"},
    {"value": "ascii", "label": "ASCII"},
    {"value": "latin-1", "label": "Latin-1"},
    {"value": "utf-16", "label": "UTF-16"},
]

DEFAULT_ENCODING = "utf-8"

# 全局默认编码（由设置页写入，连接器在设备未指定编码时取用）
_global_default = DEFAULT_ENCODING


def set_default(enc: str) -> None:
    global _global_default
    _global_default = normalize(enc)


def get_default() -> str:
    return _global_default


def normalize(enc: str | None) -> str:
    """把编码名归一到 Python 认识的写法；不认识的退回 UTF-8。"""
    if not enc:
        return DEFAULT_ENCODING
    e = enc.strip().lower().replace("_", "-")
    aliases = {
        "utf8": "utf-8", "gb2312-80": "gb2312", "cp936": "gbk", "ms936": "gbk",
        "gbk2312": "gb2312", "cp950": "big5", "sjis": "shift-jis",
        "shift-jis": "shift_jis", "euc-jp": "euc_jp", "euc-kr": "euc_kr",
        "iso-8859-1": "iso8859-1", "iso-8859-15": "iso8859-15",
        "latin1": "latin-1", "us-ascii": "ascii", "hz-gb-2312": "hz",
        "utf16": "utf-16", "windows-1252": "cp1252",
    }
    e = aliases.get(e, e)
    try:
        codecs.lookup(e)
        return e
    except LookupError:
        return DEFAULT_ENCODING


def resolve(device_encoding: str | None) -> str:
    """设备指定的编码优先，否则用全局默认。"""
    return normalize(device_encoding) if device_encoding else get_default()


def safe_decode(raw: bytes | str, enc: str | None = None) -> str:
    """字节 → 文本（一次性，不跨包）。连续流请用 StreamDecoder。"""
    if isinstance(raw, str):
        return raw
    if not raw:
        return ""
    e = normalize(enc)
    try:
        return raw.decode(e)
    except (UnicodeDecodeError, LookupError):
        # 兜底只对坏字节替换，不要整包降级到 UTF-8（那会把整包中文变成 �）
        return raw.decode(e, errors="replace")


def safe_encode(text: str, enc: str | None = None) -> bytes:
    """文本 → 字节。命令基本是 ASCII，编码错也不影响；这里仍按所选编码走。"""
    if isinstance(text, bytes):
        return text
    e = normalize(enc)
    try:
        return text.encode(e, errors="replace")
    except (UnicodeEncodeError, LookupError):
        return text.encode(DEFAULT_ENCODING, errors="replace")


class StreamDecoder:
    """跨读取包保持多字节字符完整 —— SecureCRT 的做法。

    串口/网络一次 recv 到的字节边界是随机的，GBK/GB18030 一个汉字 2~4 字节，
    很容易被切成两半。**逐包独立 decode 会出事**：
        包 = 「设置IP地址」的前 3 字节 → decode('gbk') 抛 UnicodeDecodeError
        → 降级 utf-8(errors='replace') → 整包中文全变成 U+FFFD（界面上的▯▯▯）
    用增量解码器把残缺的尾巴字节缓存起来，等下一个包补齐后再解，就和 SecureCRT 一样稳。
    """

    def __init__(self, enc: str | None = None):
        self._enc = DEFAULT_ENCODING
        self._dec = None
        self.set_encoding(enc)

    @property
    def encoding(self) -> str:
        return self._enc

    def set_encoding(self, enc: str | None) -> None:
        """切换编码：丢弃缓存的残缺字节并重建解码器（只影响之后收到的数据）。"""
        self._enc = normalize(enc)
        self._dec = codecs.getincrementaldecoder(self._enc)(errors="replace")

    def decode(self, data: bytes | str, final: bool = False) -> str:
        if isinstance(data, str):
            return data
        if not data:
            return ""
        try:
            return self._dec.decode(data, final)
        except Exception:  # noqa: BLE001
            # 状态坏了就重建，绝不让终端崩
            self._dec = codecs.getincrementaldecoder(self._enc)(errors="replace")
            try:
                return self._dec.decode(data, final)
            except Exception:  # noqa: BLE001
                return data.decode(self._enc, errors="replace")
