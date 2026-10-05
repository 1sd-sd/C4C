#!/usr/bin/env python3
"""
Stage 2: Problem Parser
从摄入的结构化文本中识别并提取每道题目。

识别能力（starter kit）:
  - "Problem N" / "问题 N" / "题 N" / "N." / "N)" 格式
  - 子题 (a), (b), (c) 或 a), b), c)
  - LaTeX 公式（$...$ 和 $$...$$）
  - 基本题型分类：计算/求解/证明/画图
  - 段落标题检测 (Questions / Problems / Additional Problems)

用法:
    python parse_problems.py input.json output.json
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

# T-box classifier (optional — falls back to keyword matching if unavailable)
_tbox_classifier = None
try:
    from classify import TBoxClassifier, classify_to_legacy_type
    _tbox_classifier = TBoxClassifier()
    if _tbox_classifier.rules:
        print(f"  [T-box] Loaded {len(_tbox_classifier.rules)} classification rules "
              f"from {_tbox_classifier.tbox_path.name}")
    else:
        _tbox_classifier = None
except Exception:
    pass  # Fall back to keyword classification


def _classify(text: str, subs: list) -> str:
    """
    Classify a problem using T-box if available, otherwise keyword fallback.
    """
    if _tbox_classifier is not None:
        # Build a problem-like dict for the classifier
        problem_dict = {
            "text": text,
            "math_expressions": extract_math_expressions(text),
            "sub_problems": [
                {
                    "text": s.get("text", "") if isinstance(s, dict) else s,
                    "math_expressions": extract_math_expressions(
                        s.get("text", "") if isinstance(s, dict) else s
                    ),
                }
                for s in subs
            ],
        }
        return classify_to_legacy_type(problem_dict, _tbox_classifier)
    else:
        sub_texts = [s.get("text", "") if isinstance(s, dict) else s for s in subs]
        return classify_problem(text, sub_texts)


# ─────────────────────────────────────────────
# 题目数据结构
# ─────────────────────────────────────────────

def make_problem(
    problem_id: str,
    text: str,
    math_expressions: list,
    problem_type: str = "calculation",
    sub_problems: list = None,
) -> dict:
    """创建一个标准的题目结构。"""
    return {
        "id": problem_id,
        "text": text.strip(),
        "math_expressions": math_expressions,
        "type": problem_type,
        "sub_problems": sub_problems or [],
    }


# ─────────────────────────────────────────────
# 段落标题检测
# ─────────────────────────────────────────────

SECTION_PATTERNS = [
    (re.compile(r"^#{1,3}\s*(?:Additional\s+)?Problems?\s*$", re.IGNORECASE), "P"),
    (re.compile(r"^#{1,3}\s*Additional\s+Problems?\s*$", re.IGNORECASE), "AP"),
    (re.compile(r"^#{1,3}\s*Questions?\s*$", re.IGNORECASE), "Q"),
    (re.compile(r"^#{1,3}\s*Part\s+([A-Z])", re.IGNORECASE), None),  # Part A, B, C...
]


def detect_section(line: str) -> Optional[str]:
    """检测段落标题，返回段落前缀或 None。"""
    stripped = line.strip()
    # Additional Problems 必须在 Problems 之前检测
    if re.match(r"^#{1,3}\s*Additional\s+Problems?\s*$", stripped, re.IGNORECASE):
        return "AP"
    if re.match(r"^#{1,3}\s*Problems?\s*$", stripped, re.IGNORECASE):
        return "P"
    if re.match(r"^#{1,3}\s*Questions?\s*$", stripped, re.IGNORECASE):
        return "Q"
    m = re.match(r"^#{1,3}\s*Part\s+([A-Z])", stripped, re.IGNORECASE)
    if m:
        return f"Part{m.group(1).upper()}"
    return None


# ─────────────────────────────────────────────
# 题号识别
# ─────────────────────────────────────────────

PROBLEM_PATTERNS = [
    re.compile(r"^(?:Problem|Prob\.?)\s+(\d+)\s*[:.：]?\s*(.*)", re.IGNORECASE),
    re.compile(r"^(?:问题|题目?|第)\s*(\d+)\s*(?:题|[:.：])?\s*(.*)"),
    re.compile(r"^(\d+)\s*[.)、．]\s+(.+)"),
    re.compile(r"^Q(\d+)\s*[:.：]?\s*(.*)", re.IGNORECASE),
    re.compile(r"^Exercise\s+(\d+)\s*[:.：]?\s*(.*)", re.IGNORECASE),
]

SUB_PROBLEM_PATTERNS = [
    re.compile(r"^\(([a-z])\)\s*(.*)"),
    re.compile(r"^([a-z])\)\s*(.*)"),
    re.compile(r"^([a-z])\.\s+(.*)"),
]


def detect_problem_start(line: str) -> Optional[tuple]:
    """检测一行是否是新题目的开始。"""
    stripped = line.strip()
    for pattern in PROBLEM_PATTERNS:
        m = pattern.match(stripped)
        if m:
            return (m.group(1), m.group(2))
    return None


def detect_sub_problem(line: str) -> Optional[tuple]:
    """检测一行是否是子题。"""
    stripped = line.strip()
    for pattern in SUB_PROBLEM_PATTERNS:
        m = pattern.match(stripped)
        if m:
            return (m.group(1), m.group(2))
    return None


# ─────────────────────────────────────────────
# 公式提取
# ─────────────────────────────────────────────

def extract_math_expressions(text: str) -> list:
    """从文本中提取 LaTeX 数学表达式。"""
    expressions = []

    for m in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        expressions.append({"type": "display", "latex": m.group(1).strip()})

    for m in re.finditer(r"\\\[(.+?)\\\]", text, re.DOTALL):
        expressions.append({"type": "display", "latex": m.group(1).strip()})

    for m in re.finditer(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", text):
        expressions.append({"type": "inline", "latex": m.group(1).strip()})

    return expressions


# ─────────────────────────────────────────────
# 题型分类
# ─────────────────────────────────────────────

TYPE_KEYWORDS = {
    "calculation": [
        "计算", "求", "compute", "calculate", "evaluate", "find",
        "integrate", "积分", "求导", "derivative", "limit", "极限",
    ],
    "equation": [
        "解方程", "solve", "求解", "方程", "equation", "system",
        "线性方程组", "linear system",
    ],
    "proof": [
        "证明", "prove", "show that", "show ", "verify", "证", "demonstrate",
    ],
    "matrix": [
        "矩阵", "matrix", "行列式", "determinant", "特征值", "eigenvalue",
        "逆矩阵", "inverse", "秩", "rank",
    ],
    "ode": [
        "微分方程", "differential equation", "ODE", "ode",
        "dy/dx", "y'", "y''",
    ],
    "graph": [
        "画图", "plot", "graph ", "sketch", "draw", "图像",
    ],
    "epsilon_delta": [
        "within", "epsilon", "delta", "ε", "δ", "varepsilon",
        "within δ", "within $\\delta$",
    ],
    "tangent": [
        "tangent line", "tangent to", "horizontal line",
        "切线", "tangent at",
    ],
    "limit": [
        "limit", "lim", "极限", "lim_", "squeeze",
    ],
    "conceptual": [
        "explain", "describe", "what does", "what do we mean",
        "is it true", "is there a", "can the", "for what kinds",
        "what is the measure", "does this answer make sense",
    ],
}


def classify_problem(text: str, sub_texts: list = None) -> str:
    """根据关键词对题目进行分类。也检查子题文本。"""
    combined = text
    if sub_texts:
        combined = text + " " + " ".join(sub_texts)
    text_lower = combined.lower()
    scores = {}
    for ptype, keywords in TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[ptype] = score

    if not scores:
        return "calculation"

    # Prioritize specific types over generic
    priority = ["epsilon_delta", "tangent", "limit", "ode", "matrix",
                "equation", "proof", "graph", "conceptual", "calculation"]
    best = max(scores, key=scores.get)

    # If tie or close, use priority
    max_score = scores[best]
    candidates = [t for t, s in scores.items() if s >= max_score - 1]
    for p in priority:
        if p in candidates:
            return p
    return best


# ─────────────────────────────────────────────
# 主解析逻辑
# ─────────────────────────────────────────────

def parse_problems(ingested_data: dict) -> list:
    """从 Stage 1 的输出中解析题目列表。"""
    raw_text = ingested_data.get("raw_text", "")
    lines = raw_text.split("\n")

    problems = []
    current_section = ""  # 段落前缀
    current_id = None
    current_lines = []
    current_subs = []
    current_sub_id = None
    current_sub_lines = []

    def flush_sub():
        nonlocal current_sub_id, current_sub_lines
        if current_sub_id and current_sub_lines:
            sub_text = "\n".join(current_sub_lines).strip()
            current_subs.append({
                "id": current_sub_id,
                "text": sub_text,
                "math_expressions": extract_math_expressions(sub_text),
            })
        current_sub_id = None
        current_sub_lines = []

    def flush_problem():
        nonlocal current_id, current_lines, current_subs
        flush_sub()
        if current_id and current_lines:
            full_text = "\n".join(current_lines).strip()
            # 生成带段落前缀的唯一 ID
            prefixed_id = f"{current_section}{current_id}" if current_section else current_id
            problems.append(make_problem(
                problem_id=prefixed_id,
                text=full_text,
                math_expressions=extract_math_expressions(full_text),
                problem_type=_classify(full_text, current_subs),
                sub_problems=current_subs,
            ))
        current_id = None
        current_lines = []
        current_subs = []

    for line in lines:
        # 检查段落标题
        section = detect_section(line)
        if section is not None:
            flush_problem()
            current_section = section
            continue

        # 标题行可能包含题号 (### Problem 1: Title)
        heading_match = re.match(r"^#{1,4}\s+(.*)", line)
        if heading_match:
            # Try to extract problem ID from heading text
            prob_in_heading = detect_problem_start(heading_match.group(1))
            if prob_in_heading:
                flush_problem()
                current_id = prob_in_heading[0]
                if prob_in_heading[1]:
                    current_lines.append(prob_in_heading[1])
                continue
            # Otherwise skip non-problem headings
            continue

        # 检查是否是新题目
        prob = detect_problem_start(line)
        if prob:
            flush_problem()
            current_id = prob[0]
            if prob[1]:
                current_lines.append(prob[1])
            continue

        # 检查是否是子题
        sub = detect_sub_problem(line)
        if sub and current_id:
            flush_sub()
            current_sub_id = sub[0]
            current_sub_lines.append(sub[1])
            continue

        # 普通行
        if current_sub_id:
            current_sub_lines.append(line)
        elif current_id:
            current_lines.append(line)

    flush_problem()
    return problems


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("用法: python parse_problems.py <输入.json> <输出.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(input_path, "r", encoding="utf-8") as f:
        ingested = json.load(f)

    print(f"[Stage 2] 题目解析: {input_path}")
    problems = parse_problems(ingested)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)

    print(f"  识别题目: {len(problems)} 道")
    for p in problems:
        sub_info = f" ({len(p['sub_problems'])} 子题)" if p["sub_problems"] else ""
        print(f"    {p['id']}: [{p['type']}]{sub_info} {p['text'][:50]}...")

    print(f"  输出: {output_path}")


if __name__ == "__main__":
    main()
