#!/usr/bin/env python3
"""
Stage 4: LaTeX Renderer
将求解结果生成专业排版的 LaTeX 作业文档。

功能:
  - 套用标准作业模板
  - 题目 + 解答交替排版
  - 数学公式正确嵌入（align, equation）
  - 编译为 PDF（如果有 LaTeX 环境）

学生扩展点:
  - 自定义模板（不同课程风格）
  - 图表插入
  - 中文支持（xelatex + ctex）
  - 多种输出格式

用法:
    python render_latex.py solutions.json output.tex [--compile]
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import date


# ─────────────────────────────────────────────
# LaTeX 模板
# ─────────────────────────────────────────────

def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _build_preamble(course: str, student: str, title: str, date_str: str,
                    cjk: bool = False) -> str:
    """Build LaTeX preamble with template values inserted.

    C4C 扩展: 检测到中文时改用 XeLaTeX + ctex 中文排版方案
    （Tectonic 内置 XeTeX 引擎，自动下载 ctex 宏包）。
    """
    if cjk:
        return (
            "\\documentclass[12pt, a4paper]{article}\n"
            "\\usepackage[UTF8]{ctex}\n"
            "\n"
            "\\usepackage{amsmath, amssymb, amsthm}\n"
            "\\usepackage{geometry}\n"
            "\\usepackage{fancyhdr}\n"
            "\\usepackage{enumitem}\n"
            "\\usepackage{xcolor}\n"
            "\\usepackage{hyperref}\n"
            "\n"
            "\\geometry{margin=1in}\n"
            "\\pagestyle{fancy}\n"
            "\\fancyhf{}\n"
            f"\\rhead{{{course}}}\n"
            f"\\lhead{{{student}}}\n"
            "\\rfoot{第 \\thepage 页}\n"
            "\n"
            "\\newcommand{\\problem}[1]{\\subsection*{题 #1}}\n"
            "\\newcommand{\\solution}{\\paragraph{解.}}\n"
            "\n"
            "\\definecolor{solutioncolor}{RGB}{0, 100, 0}\n"
            "\n"
            "\\begin{document}\n"
            "\n"
            "\\begin{center}\n"
            f"    {{\\LARGE\\bfseries {title}}} \\\\[0.5em]\n"
            f"    {{\\large {course}}} \\\\[0.3em]\n"
            f"    {student} \\quad | \\quad {date_str}\n"
            "\\end{center}\n"
            "\n"
            "\\hrule\n"
            "\\vspace{1em}\n"
        )
    return (
        "\\documentclass[12pt, a4paper]{article}\n"
        "\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage{amsmath, amssymb, amsthm}\n"
        "\\usepackage{geometry}\n"
        "\\usepackage{fancyhdr}\n"
        "\\usepackage{enumitem}\n"
        "\\usepackage{xcolor}\n"
        "\\usepackage{hyperref}\n"
        "\n"
        "\\geometry{margin=1in}\n"
        "\\pagestyle{fancy}\n"
        "\\fancyhf{}\n"
        f"\\rhead{{{course}}}\n"
        f"\\lhead{{{student}}}\n"
        "\\rfoot{Page \\thepage}\n"
        "\n"
        "\\newcommand{\\problem}[1]{\\subsection*{Problem #1}}\n"
        "\\newcommand{\\solution}{\\paragraph{Solution.}}\n"
        "\n"
        "\\definecolor{solutioncolor}{RGB}{0, 100, 0}\n"
        "\n"
        "\\begin{document}\n"
        "\n"
        "\\begin{center}\n"
        f"    {{\\LARGE\\bfseries {title}}} \\\\[0.5em]\n"
        f"    {{\\large {course}}} \\\\[0.3em]\n"
        f"    {student} \\quad | \\quad {date_str}\n"
        "\\end{center}\n"
        "\n"
        "\\hrule\n"
        "\\vspace{1em}\n"
    )


LATEX_POSTAMBLE = "\n\\end{document}\n"


# ─────────────────────────────────────────────
# 渲染函数
# ─────────────────────────────────────────────

def render_problem(solution: dict) -> str:
    """将单个题目+解答渲染为 LaTeX 片段。"""
    lines = []
    pid = solution["problem_id"]

    # 题目
    lines.append(f"\\problem{{{pid}}}")
    lines.append("")

    # 题目文本（清理 Markdown 格式）
    problem_text = clean_for_latex(solution.get("problem_text", ""))
    lines.append(problem_text)
    lines.append("")

    if solution.get("solved"):
        # 解答
        lines.append("\\solution")
        lines.append("")

        # 解题步骤
        for step in solution.get("steps", []):
            step_clean = clean_for_latex(step)
            lines.append(step_clean)
            lines.append("")

        # 最终答案（高亮）
        # C4C 扩展: 若答案本身是混合文本+行内数学（含 $），直接按段落渲染，
        # 避免嵌套 \[\boxed{$...$}\] 造成 "Missing $" 编译错误
        answer_latex = solution.get("answer_latex", "")
        if answer_latex:
            if "$" in answer_latex:
                lines.append("\\textbf{Answer:} " + answer_latex)
            else:
                lines.append("\\textbf{Answer:}")
                lines.append(f"\\[\\boxed{{{answer_latex}}}\\]")
            lines.append("")

    else:
        # 未解决
        reason = solution.get("reason", "自动求解器未能处理此题")
        lines.append(f"\\textit{{\\color{{red}} 未求解: {escape_latex(reason)}}}")
        lines.append("")

    # 子题
    for sub_sol in solution.get("sub_solutions", []):
        lines.append(render_sub_problem(sub_sol))

    lines.append("\\vspace{1em}")
    lines.append("\\hrule")
    lines.append("\\vspace{1em}")
    lines.append("")

    return "\n".join(lines)


def render_sub_problem(sub_solution: dict) -> str:
    """渲染子题。"""
    lines = []
    sid = sub_solution["problem_id"]
    # 提取子题字母
    parts = sid.split(".")
    sub_label = parts[-1] if len(parts) > 1 else sid

    lines.append(f"\\textbf{{({sub_label})}}")

    if sub_solution.get("solved"):
        for step in sub_solution.get("steps", []):
            lines.append(clean_for_latex(step))

        answer_latex = sub_solution.get("answer_latex", "")
        if answer_latex:
            if "$" in answer_latex:
                lines.append(answer_latex)
            else:
                lines.append(f"$\\boxed{{{answer_latex}}}$")
    else:
        reason = sub_solution.get("reason", "未求解")
        lines.append(f"\\textit{{\\color{{red}} {escape_latex(reason)}}}")

    lines.append("")
    return "\n".join(lines)


def render_document(
    solutions: list,
    course: str = "Course Name",
    student: str = "Student Name",
    title: str = "Homework",
    date_str: str = None,
) -> str:
    """
    将所有解答渲染为完整的 LaTeX 文档。

    Args:
        solutions: solve.py 的输出
        course: 课程名称
        student: 学生姓名
        title: 作业标题
        date_str: 日期
    """
    if date_str is None:
        date_str = date.today().isoformat()

    # C4C 扩展：检测中文，切换 ctex 中文模板
    all_text = course + student + title + " ".join(
        s.get("problem_text", "") + " ".join(s.get("steps", []))
        for s in solutions)
    cjk = _contains_cjk(all_text)

    # 构建前导部分
    preamble = _build_preamble(
        course=escape_latex(course),
        student=escape_latex(student),
        title=escape_latex(title),
        date_str=escape_latex(date_str),
        cjk=cjk,
    )

    # 渲染每道题
    body_parts = []
    for sol in solutions:
        body_parts.append(render_problem(sol))

    # 汇总统计
    total = len(solutions)
    solved = sum(1 for s in solutions if s.get("solved"))
    body_parts.append(f"\n\\vspace{{2em}}")
    body_parts.append(f"\\noindent\\textit{{Auto-generated: {solved}/{total} problems solved by SymPy.}}")

    body = "\n".join(body_parts)

    return preamble + body + LATEX_POSTAMBLE


# ─────────────────────────────────────────────
# LaTeX 转义工具
# ─────────────────────────────────────────────

def escape_latex(text: str) -> str:
    """转义 LaTeX 特殊字符（在非数学环境中）。"""
    # 不要转义已经在 $ 或 \[ \] 中的内容
    special = {
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
    }
    for char, replacement in special.items():
        text = text.replace(char, replacement)
    return text


def clean_for_latex(text: str) -> str:
    """
    清理文本以适应 LaTeX。
    保留 $...$ 和 $$...$$ 中的数学内容不转义。
    """
    # 分割数学和非数学部分
    parts = re.split(r"(\$\$.*?\$\$|\$.*?\$)", text, flags=re.DOTALL)
    cleaned = []
    for i, part in enumerate(parts):
        if part.startswith("$"):
            cleaned.append(part)  # 数学部分不处理
        else:
            cleaned.append(escape_latex(part))
    return "".join(cleaned)


# ─────────────────────────────────────────────
# PDF 编译
# ─────────────────────────────────────────────

def _find_tectonic() -> str:
    """查找 tectonic 编译器（C4C 扩展：无 LaTeX 发行版时的轻量方案）。"""
    candidates = [
        os.environ.get("TECTONIC_PATH", ""),
        "D:/tools/tectonic/tectonic.exe",
        "tectonic",
    ]
    for c in candidates:
        if not c:
            continue
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=15)
            if r.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def compile_pdf(tex_path: str, output_dir: str = None) -> bool:
    """
    编译 LaTeX → PDF。
    C4C 扩展: 优先使用 Tectonic（XeTeX 引擎，自动获取宏包，支持 ctex 中文），
    回退到本机 pdflatex/xelatex。

    返回: True 如果编译成功
    """
    tex_path = Path(tex_path)
    if output_dir is None:
        output_dir = str(tex_path.parent)

    # ── 方案 1: Tectonic ──
    tectonic = _find_tectonic()
    if tectonic:
        try:
            print("  使用 Tectonic (XeTeX) 编译...")
            env = dict(os.environ)
            env.setdefault("TECTONIC_CACHE_DIR", r"D:\tools\tectonic-cache")
            result = subprocess.run(
                [tectonic, "-X", "compile", str(tex_path),
                 "--outdir", output_dir, "--keep-logs"],
                capture_output=True, timeout=600, cwd=str(tex_path.parent),
                env=env,
            )
            pdf_path = Path(output_dir) / (tex_path.stem + ".pdf")
            if result.returncode == 0 and pdf_path.exists():
                print(f"  ✅ PDF 生成成功 (Tectonic): {pdf_path}")
                return True
            print(f"  ⚠️ Tectonic 编译失败 (exit={result.returncode})")
            err_tail = result.stdout.decode("utf-8", "ignore")[-800:]
            print("  " + err_tail.replace("\n", "\n  "))
        except subprocess.TimeoutExpired:
            print("  ⚠️ Tectonic 编译超时")
        except Exception as e:
            print(f"  ⚠️ Tectonic 异常: {e}")

    # ── 方案 2: 本机 pdflatex / xelatex ──
    for engine in ["pdflatex", "xelatex"]:
        try:
            # 检查引擎是否可用
            result = subprocess.run(
                [engine, "--version"],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                continue

            print(f"  使用 {engine} 编译...")

            # 编译 3 遍
            for pass_num in range(3):
                result = subprocess.run(
                    [
                        engine,
                        "-interaction=nonstopmode",
                        f"-output-directory={output_dir}",
                        str(tex_path),
                    ],
                    capture_output=True,
                    timeout=60,
                    cwd=str(tex_path.parent),
                )
                if result.returncode != 0 and pass_num == 2:
                    # 最后一遍编译失败
                    print(f"  ⚠️ 编译警告（可能有非致命错误）")

            pdf_name = tex_path.stem + ".pdf"
            pdf_path = Path(output_dir) / pdf_name
            if pdf_path.exists():
                print(f"  ✅ PDF 生成成功: {pdf_path}")
                return True
            else:
                print(f"  ❌ PDF 未生成")

        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            print(f"  ⚠️ {engine} 编译超时")
            continue

    print("  ⚠️ 未找到 LaTeX 编译器（pdflatex/xelatex）。")
    print("  安装提示:")
    print("    macOS: brew install --cask mactex-no-gui")
    print("    Ubuntu: sudo apt install texlive-full")
    print("    Windows: https://miktex.org/download")
    return False


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("用法: python render_latex.py <solutions.json> <output.tex> [--compile]")
        print("示例: python render_latex.py solutions.json homework.tex --compile")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    do_compile = "--compile" in sys.argv

    with open(input_path, "r", encoding="utf-8") as f:
        solutions = json.load(f)

    print(f"[Stage 4] LaTeX 生成: {len(solutions)} 道题目")

    # 渲染 LaTeX
    latex_doc = render_document(
        solutions,
        course="Mathematics",        # 学生可自定义
        student="Student Name",       # 学生可自定义
        title="Homework Solutions",   # 学生可自定义
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(latex_doc)
    print(f"  LaTeX 输出: {output_path}")

    # 编译 PDF
    if do_compile:
        print("[Stage 5] PDF 编译")
        success = compile_pdf(output_path)
        if not success:
            print("  提示: 先安装 LaTeX 环境，或在 Overleaf 上编译生成的 .tex 文件")

    print("完成!")


if __name__ == "__main__":
    main()
