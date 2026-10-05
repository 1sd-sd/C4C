#!/usr/bin/env python3
"""
Stage 1: Document Ingestion
读取作业文件（Markdown / PDF / Word / 图片），输出结构化文本。

Starter kit 仅实现 Markdown 读取。
PDF / Word / OCR 留给学生扩展（见 C4C.md Level 2）。

用法:
    python ingest.py input_file output.json
    python ingest.py homework.md problems.json
"""

import json
import re
import sys
from pathlib import Path


# ─────────────────────────────────────────────
# 核心函数：读取不同格式
# ─────────────────────────────────────────────

def read_markdown(filepath: str) -> str:
    """读取 Markdown 文件，返回原始文本。"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def read_pdf_text(filepath: str) -> str:
    """
    读取文本型 PDF。
    C4C Level 2 扩展实现：pdfplumber 逐页提取文本。
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("需要 pdfplumber: pip install pdfplumber")
    parts = []
    with pdfplumber.open(filepath) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            parts.append(f"<!-- page {i+1} -->\n{text}")
    return "\n\n".join(parts)


def read_docx(filepath: str) -> str:
    """
    读取 Word 文档。
    C4C Level 2 扩展实现：python-docx 提取段落文本（标题转 Markdown 标题）。
    """
    try:
        import docx
    except ImportError:
        raise ImportError("需要 python-docx: pip install python-docx")
    document = docx.Document(filepath)
    lines = []
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if "heading 1" in style:
            lines.append(f"# {text}")
        elif "heading 2" in style:
            lines.append(f"## {text}")
        elif "heading 3" in style:
            lines.append(f"### {text}")
        else:
            lines.append(text)
    # 表格内容也提取
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            lines.append(" | ".join(cells))
    return "\n\n".join(lines)


def read_image_ocr(filepath: str) -> str:
    """
    OCR 读取图片/扫描件。
    需要: pip install pytesseract / Pillow, 或使用 Claude Vision API
    ⚠️ Starter kit 未实现——学生扩展点。
    """
    raise NotImplementedError(
        "OCR 摄入未实现。\n"
        "提示: pip install pytesseract Pillow\n"
        "参考: pytesseract.image_to_string(Image.open(path), lang='chi_sim+eng')"
    )


# ─────────────────────────────────────────────
# 格式检测与路由
# ─────────────────────────────────────────────

FORMAT_HANDLERS = {
    ".md":   read_markdown,
    ".txt":  read_markdown,       # 纯文本同 Markdown 处理
    ".pdf":  read_pdf_text,
    ".docx": read_docx,
    ".png":  read_image_ocr,
    ".jpg":  read_image_ocr,
    ".jpeg": read_image_ocr,
}


def detect_format(filepath: str) -> str:
    """根据扩展名检测文件格式。"""
    ext = Path(filepath).suffix.lower()
    if ext not in FORMAT_HANDLERS:
        raise ValueError(f"不支持的文件格式: {ext}\n支持: {list(FORMAT_HANDLERS.keys())}")
    return ext


def ingest(filepath: str) -> dict:
    """
    主入口：读取任意格式的作业文件，返回结构化结果。

    返回:
        {
            "source_file": "homework.md",
            "format": ".md",
            "raw_text": "...",
            "sections": [
                {"title": "Section Title", "content": "..."},
                ...
            ]
        }
    """
    filepath = str(filepath)
    ext = detect_format(filepath)
    handler = FORMAT_HANDLERS[ext]

    raw_text = handler(filepath)

    # 基础分段：按 Markdown 标题或空行分段
    sections = split_into_sections(raw_text)

    return {
        "source_file": Path(filepath).name,
        "format": ext,
        "raw_text": raw_text,
        "sections": sections,
    }


def split_into_sections(text: str) -> list:
    """
    将文本按 Markdown 标题分段。
    如果没有标题，整个文本作为一个 section。
    """
    sections = []
    current_title = "Untitled"
    current_lines = []

    for line in text.split("\n"):
        # 检测 Markdown 标题
        heading_match = re.match(r"^(#{1,4})\s+(.+)", line)
        if heading_match:
            # 保存前一个 section
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append({
                        "title": current_title,
                        "content": content,
                    })
            current_title = heading_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # 保存最后一个 section
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({
                "title": current_title,
                "content": content,
            })

    return sections


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("用法: python ingest.py <输入文件> <输出.json>")
        print("示例: python ingest.py homework.md problems.json")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not Path(input_path).exists():
        print(f"错误: 文件不存在 — {input_path}")
        sys.exit(1)

    print(f"[Stage 1] 文档摄入: {input_path}")
    result = ingest(input_path)

    # 确保输出目录存在
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  格式: {result['format']}")
    print(f"  分段: {len(result['sections'])} sections")
    print(f"  输出: {output_path}")


if __name__ == "__main__":
    main()
