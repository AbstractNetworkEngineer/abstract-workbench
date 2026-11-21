"""操作手册导入：上传 PDF/Word/TXT，提取纯文本，注入 AI 上下文。"""

from pathlib import Path

from sqlalchemy.orm import Session

from database import DATA_DIR
from models import Manual, Setting

MANUAL_DIR = DATA_DIR / "manuals"
MANUAL_DIR.mkdir(exist_ok=True)


def resolve_manual_path(stored: str | None) -> Path | None:
    """解析手册文件路径；项目搬迁导致绝对路径失效时，按文件名回退到当前 manuals 目录。

    手册记录里存的是落盘时的绝对路径。整个项目被移动到别的盘/目录后这些路径就失效了，
    但文件本身还在 data/manuals 里 —— 按文件名回退即可恢复，不必重新导入。
    """
    if not stored:
        return None
    p = Path(stored)
    if p.exists():
        return p
    fallback = MANUAL_DIR / p.name
    return fallback if fallback.exists() else None

# 不再限制单个文档大小与份数；仅保留 AI 单次注入的上下文预算
MAX_CONTEXT_CHARS = 10_000

SUPPORTED = {".txt": "txt", ".md": "txt", ".log": "txt", ".cfg": "txt", ".conf": "txt",
             ".pdf": "pdf", ".docx": "docx"}


def extract_text(path: Path, kind: str) -> str:
    if kind == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                parts.append("")
        return "\n".join(parts)
    if kind == "docx":
        import docx

        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    # 纯文本：优先 UTF-8，回退 GBK
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def save_manual_from_path(db: Session, filename: str, raw_path: Path) -> Manual:
    """从已落盘的原始文件提取文本并登记（文件大小不设上限）。"""
    suffix = Path(filename).suffix.lower()
    kind = SUPPORTED.get(suffix)
    if kind is None:
        raise ValueError(f"不支持的格式 {suffix}，请上传 PDF / Word(.docx) / TXT")

    text = extract_text(raw_path, kind)  # 不截断
    text_path = raw_path.with_suffix(raw_path.suffix + ".txt")
    text_path.write_text(text, encoding="utf-8")

    manual = Manual(
        filename=Path(filename).name,
        kind=kind,
        chars=len(text),
        file_path=str(raw_path),
        text_path=str(text_path),
    )
    db.add(manual)
    db.commit()
    db.refresh(manual)
    return manual


def delete_manual(db: Session, manual_id: int) -> bool:
    m = db.get(Manual, manual_id)
    if not m:
        return False
    for p in (m.file_path, m.text_path):
        try:
            if p:
                Path(p).unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(m)
    db.commit()
    return True


def get_manual_context(db: Session) -> str:
    """拼接手册上下文（设置页补充摘录 + 已导入手册），按预算截断。"""
    chunks = []
    row = db.get(Setting, "ai_manual")
    if row and row.value:
        chunks.append("# 补充摘录\n" + row.value)

    manuals = db.query(Manual).order_by(Manual.id.desc()).all()
    budget = MAX_CONTEXT_CHARS - sum(len(c) for c in chunks)
    for m in manuals:
        if budget <= 0:
            break
        p = resolve_manual_path(m.text_path)
        if p is None:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        segment = f"# 手册: {m.filename}\n" + text
        if len(segment) > budget:
            segment = segment[:budget] + "\n…(已截断)"
        chunks.append(segment)
        budget -= len(segment)

    return "\n\n".join(chunks)[:MAX_CONTEXT_CHARS]
