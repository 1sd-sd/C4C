#!/usr/bin/env python3
"""
一键流水线：串联 Stage 1-5，从作业文件到 PDF。

用法:
    python pipeline.py <输入文件> <输出目录> [选项]

示例:
    python pipeline.py examples/sample_homework.md output/
    python pipeline.py homework.pdf output/ --compile
    python pipeline.py homework.docx output/ --course "Linear Algebra" --student "张三"

选项:
    --compile           编译 PDF（需要 LaTeX 环境）
    --course NAME       课程名称（默认: Mathematics）
    --student NAME      学生姓名（默认: Student）
    --title TITLE       作业标题（默认: Homework Solutions）
    --verbose           显示详细输出
"""

import argparse
import json
import sys
import time
from pathlib import Path

# 添加 scripts 目录到 path
scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(scripts_dir))

# ── Auto-install dependencies if missing ──────────────
from bootstrap import ensure_dependencies, SKILL_ROOT
ensure_dependencies()

from ingest import ingest
from parse_problems import parse_problems
from solve import solve_all
from render_latex import render_document, compile_pdf


def run_pipeline(
    input_path: str,
    output_dir: str,
    course: str = "Mathematics",
    student: str = "Student",
    title: str = "Homework Solutions",
    do_compile: bool = False,
    verbose: bool = False,
):
    """
    执行完整的作业求解流水线。

    Stage 1: 文档摄入 → problems.json
    Stage 2: 题目解析 → parsed.json
    Stage 3: 自动求解 → solutions.json
    Stage 4: LaTeX 生成 → homework.tex
    Stage 5: PDF 编译 → homework.pdf (可选)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    print("=" * 60)
    print("🚀 作业自动求解流水线")
    print(f"   输入: {input_path}")
    print(f"   输出: {output_dir}")
    print("=" * 60)

    # ── Stage 1: 文档摄入 ──────────────────────
    print("\n📄 Stage 1: 文档摄入")
    try:
        ingested = ingest(input_path)
        ingested_path = output_dir / "1_ingested.json"
        with open(ingested_path, "w", encoding="utf-8") as f:
            json.dump(ingested, f, ensure_ascii=False, indent=2)
        print(f"   ✅ 格式: {ingested['format']}, 分段: {len(ingested['sections'])}")
    except Exception as e:
        print(f"   ❌ 摄入失败: {e}")
        sys.exit(1)

    # ── Stage 2: 题目解析 ──────────────────────
    print("\n🔍 Stage 2: 题目解析")
    try:
        problems = parse_problems(ingested)
        parsed_path = output_dir / "2_parsed.json"
        with open(parsed_path, "w", encoding="utf-8") as f:
            json.dump(problems, f, ensure_ascii=False, indent=2)
        print(f"   ✅ 识别题目: {len(problems)} 道")
        for p in problems:
            subs = f" ({len(p['sub_problems'])} 子题)" if p["sub_problems"] else ""
            print(f"      Problem {p['id']}: [{p['type']}]{subs}")
    except Exception as e:
        print(f"   ❌ 解析失败: {e}")
        sys.exit(1)

    if not problems:
        print("\n⚠️ 未识别到任何题目。请检查输入文件格式。")
        print("   支持的题号格式: 'Problem N' / '题 N' / 'N.' / 'N)' / 'Q.N'")
        sys.exit(1)

    # ── Stage 3: 自动求解 ──────────────────────
    print("\n🧮 Stage 3: 自动求解")
    try:
        solutions = solve_all(problems)
        solutions_path = output_dir / "3_solutions.json"
        with open(solutions_path, "w", encoding="utf-8") as f:
            json.dump(solutions, f, ensure_ascii=False, indent=2)

        solved = sum(1 for s in solutions if s["solved"])
        total = len(solutions)
        print(f"   ✅ 求解完成: {solved}/{total}")
        for s in solutions:
            status = "✅" if s["solved"] else "❌"
            info = s.get("answer_latex", s.get("reason", ""))[:50]
            print(f"      {status} Problem {s['problem_id']}: {info}")
    except Exception as e:
        print(f"   ❌ 求解失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ── Stage 3b: 国产 LLM 兜底求解（DeepSeek/Qwen/Kimi）──
    # 省钱策略：仅对 SymPy 未解出的题目调用；多题合并为一次调用；结果落盘缓存。
    try:
        from llm_engine import is_available, batch_solve
        if is_available():
            unsolved_problems = [p for p, s in zip(problems, solutions) if not s.get("solved")]
            if unsolved_problems:
                print(f"\n🤖 Stage 3b: 国产 LLM 兜底求解（{len(unsolved_problems)} 道 SymPy 未解）")
                llm_solutions = batch_solve(unsolved_problems, verbose=True)
                llm_by_id = {str(s["problem_id"]): s for s in llm_solutions}
                for s in solutions:
                    merged = llm_by_id.get(str(s["problem_id"]))
                    if merged and merged.get("solved"):
                        s.update(merged)
                # 重新保存 solutions
                with open(solutions_path, "w", encoding="utf-8") as f:
                    json.dump(solutions, f, ensure_ascii=False, indent=2)
                solved = sum(1 for s in solutions if s["solved"])
                print(f"   ✅ LLM 兜底后: {solved}/{len(solutions)}")
            else:
                print("\n🤖 Stage 3b: 全部题目 SymPy 已解出，0 次 API 调用")
        else:
            print("\n🤖 Stage 3b: 未配置国产模型 API Key，跳过 LLM 兜底"
                  "（设置 DEEPSEEK_API_KEY 后启用）")
    except ImportError:
        print("\n🤖 Stage 3b: llm_engine 模块缺失，跳过")

    # ── Stage 4: LaTeX 生成 ──────────────────────
    print("\n📝 Stage 4: LaTeX 生成")
    try:
        tex_content = render_document(
            solutions,
            course=course,
            student=student,
            title=title,
        )
        tex_path = output_dir / "homework.tex"
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)
        print(f"   ✅ LaTeX 文件: {tex_path}")
    except Exception as e:
        print(f"   ❌ LaTeX 生成失败: {e}")
        sys.exit(1)

    # ── Stage 5: PDF 编译（可选）──────────────
    if do_compile:
        print("\n📑 Stage 5: PDF 编译")
        success = compile_pdf(str(tex_path), str(output_dir))
        if success:
            pdf_path = output_dir / "homework.pdf"
            print(f"   ✅ PDF 文件: {pdf_path}")
        else:
            print("   ⚠️ PDF 编译失败（可能未安装 LaTeX）")
            print("   替代方案: 将 homework.tex 上传到 overleaf.com 在线编译")
    else:
        print("\n📑 Stage 5: PDF 编译（跳过）")
        print("   添加 --compile 参数启用 PDF 编译")

    # ── 汇总 ──────────────────────────────────
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("📊 流水线执行完成")
    print(f"   耗时: {elapsed:.1f} 秒")
    print(f"   题目: {total} 道")
    print(f"   已解: {solved} 道 ({100*solved/total:.0f}%)")
    print(f"   输出文件:")
    for f in sorted(output_dir.iterdir()):
        size = f.stat().st_size
        print(f"      {f.name} ({size:,} bytes)")
    print("=" * 60)

    return {
        "total": total,
        "solved": solved,
        "output_dir": str(output_dir),
        "elapsed": elapsed,
    }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="作业自动求解流水线: 文件 → 解析 → 求解 → LaTeX → PDF"
    )
    parser.add_argument("input", help="输入文件路径 (md/pdf/docx/图片)")
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument("--compile", action="store_true", help="编译 PDF")
    parser.add_argument("--course", default="Mathematics", help="课程名称")
    parser.add_argument("--student", default="Student", help="学生姓名")
    parser.add_argument("--title", default="Homework Solutions", help="作业标题")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在 — {args.input}")
        sys.exit(1)

    run_pipeline(
        input_path=args.input,
        output_dir=args.output_dir,
        course=args.course,
        student=args.student,
        title=args.title,
        do_compile=args.compile,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
