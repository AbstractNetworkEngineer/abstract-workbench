"""知识库：手册分块检索（本地关键词打分，不外传）+ 环境记忆。"""

import math
import re
from pathlib import Path

from sqlalchemy.orm import Session

from models import Manual, Setting
from services.manuals import resolve_manual_path

CHUNK_CHARS = 600
TOP_K = 5
BUDGET = 6000


def _chunks(text: str) -> list[str]:
    lines = text.splitlines()
    out, buf = [], []
    size = 0
    for ln in lines:
        buf.append(ln)
        size += len(ln) + 1
        if size >= CHUNK_CHARS:
            out.append("\n".join(buf))
            buf, size = [], 0
    if buf:
        out.append("\n".join(buf))
    return out


def _terms(query: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[\w一-鿿]{2,}", query)}


def retrieve(db: Session, query: str, top_k: int = TOP_K, budget: int = BUDGET) -> str:
    """按问题检索手册相关段落（关键词重叠打分）。"""
    if not query.strip():
        return ""
    terms = _terms(query)
    if not terms:
        return ""
    scored: list[tuple[float, str, str]] = []
    for m in db.query(Manual).order_by(Manual.id.desc()).all():
        p = resolve_manual_path(m.text_path)
        if p is None:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for ch in _chunks(text):
            low = ch.lower()
            hit = sum(1 for t in terms if t in low)
            if hit:
                score = hit / math.sqrt(len(ch) + 1)
                scored.append((score, m.filename, ch))
    scored.sort(key=lambda x: -x[0])
    parts, used = [], 0
    for _, fname, ch in scored[:top_k]:
        seg = f"【手册: {fname}】\n{ch}"
        if used + len(seg) > budget:
            seg = seg[: max(0, budget - used)]
            if not seg:
                break
        parts.append(seg)
        used += len(seg)
    return "\n\n".join(parts)


def full_context(db: Session, query: str = "") -> str:
    """AI 注入上下文：补充摘录 + 环境记忆 +（问题检索段落 或 全量手册头）。"""
    chunks = []
    row = db.get(Setting, "ai_manual")
    if row and row.value:
        chunks.append("# 补充摘录\n" + row.value)
    mem = db.get(Setting, "env_memory")
    if mem and mem.value:
        chunks.append("# 环境记忆（拓扑/命名/习惯）\n" + mem.value)

    retrieved = retrieve(db, query) if query else ""
    if retrieved:
        chunks.append("# 操作手册相关段落\n" + retrieved)
    else:
        # 无问题时注入各手册开头，保证基础上下文
        budget = BUDGET
        for m in db.query(Manual).order_by(Manual.id.desc()).all():
            if budget <= 0:
                break
            p = resolve_manual_path(m.text_path)
            if p is None:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            seg = f"# 手册: {m.filename}\n" + text
            if len(seg) > budget:
                seg = seg[:budget] + "\n…(截断)"
            chunks.append(seg)
            budget -= len(seg)
    return "\n\n".join(chunks)[: BUDGET + 2000]


def _manual_texts(db: Session) -> list[str]:
    out = []
    for m in db.query(Manual).order_by(Manual.id.desc()).all():
        p = resolve_manual_path(m.text_path)
        if p is None:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if t.strip():
            out.append(t)
    return out


def verify_commands(db: Session, commands: list[str]) -> list[dict]:
    """把 AI 生成的命令逐条对照手册查证，让"设备是否真支持"可被人工核实。

    status: verified（手册中出现完整命令）/ partial（只命中首关键字）/ unverified（手册中查无此命令）
    """
    texts = _manual_texts(db)
    corpus = "\n".join(texts).lower()
    checks: list[dict] = []
    for raw in commands:
        cmd = (raw or "").strip()
        if not cmd:
            continue
        low = cmd.lower()
        first = low.split()[0] if low.split() else ""
        if low in corpus:
            status = "verified"
            note = "手册中已出现完整命令"
        elif first and len(first) > 2 and first in corpus:
            status = "partial"
            note = f"手册中只有关键字 `{first}`，完整写法未找到"
        else:
            status = "unverified"
            note = "手册中查无此命令，可能是臆造或型号不支持"
        checks.append({"command": cmd, "status": status, "note": note})
    return checks
