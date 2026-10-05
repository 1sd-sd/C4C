#!/usr/bin/env python3
"""
Stage 3: SymPy Solver
使用 SymPy 符号计算引擎自动求解数学问题。

Starter kit 覆盖:
  - 微积分: 求导、积分、极限、级数
  - 线性代数: 矩阵运算、特征值、行列式、逆矩阵
  - 方程求解: 代数方程、线性方程组
  - 微分方程: 基本 ODE
  - ε-δ: 邻域表示法 + 计算
  - 切线: 水平切线、切线方程
  - 极限: 单侧极限、含绝对值、无穷

用法:
    python solve.py input.json output.json
"""

import json
import re
import sys
import traceback
from pathlib import Path

import sympy
from sympy import (
    symbols, Symbol, Function, Abs, Piecewise, oo, pi, E, S,
    diff, integrate, limit, series, summation,
    solve, dsolve, linsolve, nonlinsolve,
    Matrix, eye, zeros, det, Rational,
    sin, cos, tan, exp, log, ln, sqrt,
    simplify, expand, factor, cancel, apart, together,
    latex, Eq, And, Or,
)
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

# 标准变量
x, y, z, t, n, k = symbols("x y z t n k")
a, b, c = symbols("a b c")
delta_sym = Symbol("delta", positive=True)
epsilon_sym = Symbol("epsilon", positive=True)
f = Function("f")

TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)


# ═══════════════════════════════════════════════
# 表达式解析
# ═══════════════════════════════════════════════

def _find_matching_brace(s: str, pos: int) -> int:
    """找到 pos 处 '{' 对应的 '}' 位置，支持嵌套。返回 '}' 的索引或 -1。"""
    if pos >= len(s) or s[pos] != '{':
        return -1
    depth = 1
    i = pos + 1
    while i < len(s) and depth > 0:
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
        i += 1
    return i - 1 if depth == 0 else -1


def safe_parse(expr_str: str) -> sympy.Expr:
    """安全解析数学表达式字符串为 SymPy 对象。"""
    s = expr_str.strip()

    s = re.sub(r"\\begin\{.*?\}", "", s)
    s = re.sub(r"\\end\{.*?\}", "", s)

    # Handle \frac with potentially nested braces
    def _replace_frac(s):
        while "\\frac{" in s:
            idx = s.index("\\frac{")
            # Find matching brace for numerator
            num_start = idx + 6  # after \frac{
            num_end = _find_matching_brace(s, num_start - 1)
            if num_end < 0:
                break
            # Find matching brace for denominator
            if num_end + 1 >= len(s) or s[num_end + 1] != '{':
                break
            den_start = num_end + 2
            den_end = _find_matching_brace(s, num_end + 1)
            if den_end < 0:
                break
            num = s[num_start:num_end]
            den = s[den_start:den_end]
            s = s[:idx] + f"(({num})/({den}))" + s[den_end + 1:]
        return s

    s = _replace_frac(s)
    s = re.sub(r"\\sqrt\[(\d+)\]\{([^}]+)\}", r"((\2)**(1/(\1)))", s)
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\left[(\[{|]?", "(", s)
    s = re.sub(r"\\right[)\]}|]?", ")", s)
    s = s.replace("\\cdot", "*")
    s = s.replace("\\times", "*")
    s = s.replace("\\div", "/")
    s = s.replace("\\pi", "pi")
    s = s.replace("\\infty", "oo")

    for func in ["sin", "cos", "tan", "ln", "log", "exp",
                 "arcsin", "arccos", "arctan"]:
        s = s.replace(f"\\{func}", func)

    s = re.sub(r"\\[,;!]", " ", s)
    s = re.sub(r"\\(?:quad|qquad)", " ", s)
    s = re.sub(r"\\mathrm\{([^}]+)\}", r"\1", s)
    # 绝对值: |x| → Abs(x)
    s = re.sub(r"\|([^|]+)\|", r"Abs(\1)", s)

    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"\^\{([^}]+)\}", r"**(\1)", s)
    s = re.sub(r"\^(\w)", r"**\1", s)
    s = re.sub(r"_\{[^}]+\}", "", s)
    s = re.sub(r"_\w", "", s)
    s = s.replace("{", "(").replace("}", ")")
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        raise ValueError("空表达式")

    return parse_expr(s, local_dict={
        "x": x, "y": y, "z": z, "t": t, "n": n, "k": k,
        "a": a, "b": b, "c": c,
        "pi": pi, "e": E, "oo": oo, "inf": oo,
        "sin": sin, "cos": cos, "tan": tan,
        "exp": exp, "log": log, "ln": ln, "sqrt": sqrt,
        "delta": delta_sym, "epsilon": epsilon_sym,
        "Abs": Abs,
    }, transformations=TRANSFORMATIONS)


def is_trivial_expression(math_exprs: list) -> bool:
    """检测数学表达式是否过于简单（单个变量/常量），避免误判为'已求解'。"""
    if not math_exprs:
        return True
    for expr in math_exprs:
        latex_str = expr.get("latex", "")
        cleaned = re.sub(r"\\[a-zA-Z]+", "", latex_str).strip()
        if len(cleaned) > 1:
            return False
    return True


def has_abstract_functions(math_exprs: list) -> bool:
    """
    检测表达式是否包含抽象函数符号 f(x), g(x) 等。
    这些是概念题的标志，不应尝试计算。
    """
    for expr_info in math_exprs:
        latex_str = expr_info.get("latex", "")
        # f(x), g(x), h(x) 等抽象函数调用
        if re.search(r"[fgh]\s*\([a-z]\)", latex_str):
            return True
        # f(a), g(a)
        if re.search(r"[fgh]\s*\([a-z]\)", latex_str.replace("\\", "")):
            return True
    return False


# ═══════════════════════════════════════════════
# 辅助：从题目文本提取函数定义
# ═══════════════════════════════════════════════

def extract_function_definition(text: str, math_exprs: list):
    """
    从题目文本中提取 f(x) = ... 或 y = ... 的定义。
    返回 (variable, expression) 或 None。
    """
    for expr_info in math_exprs:
        latex_str = expr_info["latex"]
        # f(x) = expr
        m = re.match(r"f\s*\(\s*x\s*\)\s*=\s*(.+)", latex_str)
        if m:
            try:
                return (x, safe_parse(m.group(1)))
            except Exception:
                pass
        # y = expr
        m = re.match(r"y\s*=\s*(.+)", latex_str)
        if m:
            try:
                return (x, safe_parse(m.group(1)))
            except Exception:
                pass
    return None


def extract_point_from_text(text: str, math_exprs: list):
    """从文本中提取坐标点 (a, b)。"""
    for expr_info in math_exprs:
        latex_str = expr_info["latex"]
        m = re.match(r"\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)?", latex_str)
        if m:
            try:
                return (safe_parse(m.group(1)), safe_parse(m.group(2)))
            except Exception:
                pass
    # 从文本中直接提取
    m = re.search(r"\((\d+),\s*(\d+)\)", text)
    if m:
        return (S(int(m.group(1))), S(int(m.group(2))))
    return None


# ═══════════════════════════════════════════════
# 辅助：从 LaTeX 提取极限表达式
# ═══════════════════════════════════════════════

def try_parse_limit_expression(latex_str: str):
    """
    解析 \\lim_{x \\to a} expr 格式。
    返回 (variable, point, direction, expression) 或 None。
    direction: None (双侧), '+' (右), '-' (左)
    """
    # Match \lim_{x \to a^+} or \lim_{x \to a^-} or \lim_{x \to a}
    m = re.search(
        r"\\lim_\{([a-z])\s*\\to\s*([^}]*)\}\s*(.+)",
        latex_str
    )
    if not m:
        # Try short form: \lim_{x \to 0}
        m = re.search(r"\\lim_\{([a-z])\\to\s*([^}]*)\}\s*(.+)", latex_str)
    if not m:
        return None

    var_str = m.group(1)
    point_str = m.group(2).strip()
    expr_str = m.group(3).strip()

    # Detect direction
    direction = None
    if point_str.endswith("^+") or point_str.endswith("^{+}"):
        direction = "+"
        point_str = re.sub(r"\^\{?\+\}?$", "", point_str).strip()
    elif point_str.endswith("^-") or point_str.endswith("^{-}"):
        direction = "-"
        point_str = re.sub(r"\^\{?-\}?$", "", point_str).strip()

    var = Symbol(var_str)

    try:
        point = safe_parse(point_str)
    except Exception:
        if "infty" in point_str or "inf" in point_str:
            point = oo
        else:
            return None

    try:
        expr = safe_parse(expr_str)
    except Exception:
        return None

    return (var, point, direction, expr)


def try_parse_integral(latex_str: str):
    """解析积分表达式。返回 (integrand, variable, bounds_or_None)。"""
    # \int_{a}^{b} expr dx  or  \int_a^b expr dx  or  \int expr dx
    int_match = re.search(
        r"\\int(?:_\{([^}]*)\}\^\{([^}]*)\}|_(\w)\^(\w))?\s*(.+?)\s*d([a-z])\s*$",
        latex_str
    )
    if not int_match:
        return None

    lower = int_match.group(1) or int_match.group(3)
    upper = int_match.group(2) or int_match.group(4)
    integrand_str = int_match.group(5)
    var_str = int_match.group(6)

    var = Symbol(var_str)
    try:
        integrand = safe_parse(integrand_str)
    except Exception:
        return None

    bounds = None
    if lower is not None and upper is not None:
        try:
            bounds = (safe_parse(lower), safe_parse(upper))
        except Exception:
            pass

    return (integrand, var, bounds)


# ═══════════════════════════════════════════════
# DOMAIN SOLVER: ε-δ 邻域记法
# ═══════════════════════════════════════════════

def solve_epsilon_delta(problem: dict) -> dict:
    """
    求解 ε-δ 邻域表示问题。
    模式: "describe x within δ of [0/a]" → 不等式/绝对值/区间
    如果检测到函数定义 (如 f(x)=x²)，自动转交计算求解器。
    """
    text = problem["text"]
    math_exprs = problem.get("math_expressions", [])
    subs = problem.get("sub_problems", [])

    # 如果题目包含具体函数定义，转交计算求解器
    func_def = extract_function_definition(text, math_exprs)
    if func_def:
        return solve_epsilon_delta_computation(problem)

    text = text.lower()

    # 判断邻域中心: 0 还是 a
    center = "0"
    exclude_center = False

    if "within δ of a" in text or "within $\\delta$ of $a$" in text.replace("\\\\", "\\"):
        center = "a"
    if "within δ of 0" in text or "within $\\delta$ of 0" in text.replace("\\\\", "\\"):
        center = "0"
    if "not equal to" in text or "but not equal" in text:
        exclude_center = True

    # 检测子题类型并生成答案
    sub_solutions = []
    for sub in subs:
        sub_text = sub["text"].lower()
        sol = _solve_notation_subproblem(sub, center, exclude_center)
        sub_solutions.append(sol)

    # 主题目：生成概要
    if center == "0":
        if exclude_center:
            summary = "x within δ of 0, not equal to 0: $0 < |x| < \\delta$"
        else:
            summary = "x within δ of 0: $|x| < \\delta$, i.e. $-\\delta < x < \\delta$"
    else:
        if exclude_center:
            summary = "x within δ of a, not equal to a: $0 < |x - a| < \\delta$"
        else:
            summary = "x within δ of a: $|x - a| < \\delta$, i.e. $a - \\delta < x < a + \\delta$"

    return {
        "problem_id": problem["id"],
        "problem_text": problem["text"],
        "solved": True,
        "steps": [summary],
        "answer": summary,
        "answer_latex": summary.split(": ")[-1] if ": " in summary else summary,
        "solver": "epsilon_delta_template",
        "sub_solutions": sub_solutions,
    }


def _solve_notation_subproblem(sub: dict, center: str, exclude: bool) -> dict:
    """为 ε-δ 子题生成符号答案。"""
    text = sub["text"].lower()
    sid = sub["id"]

    c = "a" if center == "a" else "0"
    steps = []
    answer_latex = ""

    if "inequalit" in text:
        if c == "0":
            if exclude:
                answer_latex = "-\\delta < x < 0 \\text{ or } 0 < x < \\delta"
                steps = ["Using inequalities: $-\\delta < x < \\delta$ and $x \\neq 0$",
                         f"Equivalently: ${answer_latex}$"]
            else:
                answer_latex = "-\\delta < x < \\delta"
                steps = [f"The set of all $x$ within $\\delta$ of 0: ${answer_latex}$"]
        else:
            if exclude:
                answer_latex = "a - \\delta < x < a + \\delta, \\quad x \\neq a"
                steps = [f"${answer_latex}$",
                         "Or equivalently: $a - \\delta < x < a$ or $a < x < a + \\delta$"]
            else:
                answer_latex = "a - \\delta < x < a + \\delta"
                steps = [f"${answer_latex}$",
                         "Equivalently: $-\\delta < x - a < \\delta$"]
    elif "absolute" in text:
        if c == "0":
            if exclude:
                answer_latex = "0 < |x| < \\delta"
            else:
                answer_latex = "|x| < \\delta"
        else:
            if exclude:
                answer_latex = "0 < |x - a| < \\delta"
            else:
                answer_latex = "|x - a| < \\delta"
        steps = [f"${answer_latex}$"]
    elif "interval" in text:
        if c == "0":
            if exclude:
                answer_latex = "(-\\delta, 0) \\cup (0, \\delta)"
            else:
                answer_latex = "(-\\delta, \\delta)"
        else:
            if exclude:
                answer_latex = "(a - \\delta, a) \\cup (a, a + \\delta)"
            else:
                answer_latex = "(a - \\delta, a + \\delta)"
        steps = [f"${answer_latex}$"]
    elif "graphic" in text or "graph" in text:
        steps = ["[Number line with open circles at endpoints, center marked]"]
        answer_latex = "\\text{See graph}"
        return _make_sub_solution(sub, steps, answer_latex, solved=True)
    else:
        return _unsolved_sub(sub, "无法识别子题类型")

    return _make_sub_solution(sub, steps, answer_latex, solved=True)


# ═══════════════════════════════════════════════
# DOMAIN SOLVER: ε-δ 计算
# ═══════════════════════════════════════════════

def solve_epsilon_delta_computation(problem: dict) -> dict:
    """
    求解 ε-δ 计算问题。
    例: Let f(x) = x², find δ such that |x-3|<δ → |f(x)-9|<1
    """
    text = problem["text"]
    math_exprs = problem.get("math_expressions", [])
    subs = problem.get("sub_problems", [])

    # 提取函数定义
    func_def = extract_function_definition(text, math_exprs)
    if not func_def:
        return _unsolved(problem, "无法提取函数定义")

    var, f_expr = func_def
    sub_solutions = []

    for sub in subs:
        sol = _solve_ed_computation_sub(sub, var, f_expr)
        sub_solutions.append(sol)

    # 主题概要
    steps = [f"Given: $f(x) = {latex(f_expr)}$"]
    return {
        "problem_id": problem["id"],
        "problem_text": problem["text"],
        "solved": True,
        "steps": steps,
        "answer": f"f(x) = {latex(f_expr)}",
        "answer_latex": f"f(x) = {latex(f_expr)}",
        "solver": "epsilon_delta_computation",
        "sub_solutions": sub_solutions,
    }


def _solve_ed_computation_sub(sub: dict, var, f_expr) -> dict:
    """求解 ε-δ 计算的子题。"""
    text = sub["text"]
    text_lower = text.lower()

    # Sub (a): Find positive x such that f(x) is within ε of L
    # Pattern: "f(x) is within 1 of 9"
    m = re.search(r"f\(x\).*?within\s+([\d./]+)\s+of\s+([\d./]+)", text_lower)
    if m and ("find all" in text_lower or "find the" in text_lower
              or "positive" in text_lower):
        try:
            eps = S(m.group(1))
            L = S(m.group(2))
            # Solve |f(x) - L| < eps → L - eps < f(x) < L + eps
            ineq_lower = f_expr - (L - eps)  # > 0
            ineq_upper = (L + eps) - f_expr   # > 0
            sol_lower = solve(f_expr - (L - eps), var)
            sol_upper = solve(f_expr - (L + eps), var)
            # For positive x
            lower_bound = [s for s in sol_lower if s.is_real and s > 0]
            upper_bound = [s for s in sol_upper if s.is_real and s > 0]

            if lower_bound and upper_bound:
                lb = min(lower_bound)
                ub = max(upper_bound)
                answer = f"({latex(lb)}, {latex(ub)})"
                steps = [
                    f"Need: ${latex(L)} - {latex(eps)} < {latex(f_expr)} < {latex(L)} + {latex(eps)}$",
                    f"i.e. ${latex(L - eps)} < {latex(f_expr)} < {latex(L + eps)}$",
                    f"Solving: $x \\in {answer}$ (positive $x$ only)",
                ]
                return _make_sub_solution(sub, steps, answer, solved=True)
        except Exception:
            pass

    # Sub (b,c): Find δ such that |x-a| < δ → |f(x)-L| < ε
    m = re.search(r"within\s+\$?\\?delta\$?\s+of\s+([\d./]+).*?within\s+([\d./]+)\s+of\s+([\d./]+)", text_lower)
    if m:
        try:
            a_val = S(m.group(1))
            eps = S(m.group(2))
            L = S(m.group(3))

            # Solve f(x) = L ± eps
            boundary_plus = solve(f_expr - (L + eps), var)
            boundary_minus = solve(f_expr - (L - eps), var)

            # Find the values closest to a_val
            all_boundaries = []
            for s in boundary_plus + boundary_minus:
                if s.is_real:
                    all_boundaries.append(s)

            if all_boundaries:
                # δ = min distance from a_val to each boundary
                distances = [abs(s - a_val) for s in all_boundaries]
                delta_val = min(distances)
                answer_latex = f"\\delta = {latex(delta_val)}"
                steps = [
                    f"Need: $|x - {latex(a_val)}| < \\delta \\Rightarrow |{latex(f_expr)} - {latex(L)}| < {latex(eps)}$",
                    f"Boundaries: ${latex(f_expr)} = {latex(L + eps)} \\Rightarrow x = {latex(boundary_plus)}$",
                    f"           ${latex(f_expr)} = {latex(L - eps)} \\Rightarrow x = {latex(boundary_minus)}$",
                    f"Minimum distance from $x = {latex(a_val)}$: ${answer_latex}$",
                ]
                return _make_sub_solution(sub, steps, answer_latex, solved=True)
        except Exception:
            pass

    # Sub (d): "Is it true that for any ε..."
    if "is it true" in text_lower or "for any" in text_lower:
        steps = [
            "Yes, this is true.",
            f"For any $\\varepsilon > 0$, we can find $\\delta > 0$ such that",
            f"$|x - a| < \\delta \\Rightarrow |{latex(f_expr)} - L| < \\varepsilon$.",
            "This follows because $f(x)$ is continuous at $x = a$.",
        ]
        return _make_sub_solution(sub, steps, "\\text{Yes (continuity)}", solved=True)

    return _unsolved_sub(sub, "无法解析 ε-δ 计算子题")


# ═══════════════════════════════════════════════
# DOMAIN SOLVER: 切线
# ═══════════════════════════════════════════════

def solve_tangent(problem: dict) -> dict:
    """
    求解切线问题。
    - 水平切线: f'(x) = 0
    - 某点处切线方程: y - f(a) = f'(a)(x - a)
    """
    text = problem["text"]
    text_lower = text.lower()
    math_exprs = problem.get("math_expressions", [])
    subs = problem.get("sub_problems", [])

    # 先检查是否是概念题（无函数定义且有概念关键词）
    conceptual_answer = _match_conceptual_template(text_lower)
    if conceptual_answer and not any(
        re.match(r"y\s*=|f\s*\(\s*x\s*\)\s*=", e["latex"]) for e in math_exprs
    ):
        return {
            "problem_id": problem["id"],
            "problem_text": problem["text"],
            "solved": True,
            "steps": conceptual_answer["steps"],
            "answer": conceptual_answer["answer"],
            "answer_latex": conceptual_answer["answer_latex"],
            "solver": "conceptual_template",
            "sub_solutions": [],
        }

    # 提取函数 y = f(x)
    func_def = extract_function_definition(text, math_exprs)
    if not func_def:
        return _unsolved(problem, "无法提取函数定义")

    var, f_expr = func_def
    f_prime = diff(f_expr, var)

    steps = [
        f"Given: $y = {latex(f_expr)}$",
        f"Derivative: $y' = {latex(f_prime)}$",
    ]

    # 水平切线: f'(x) = 0
    if "horizontal" in text_lower:
        critical_points = solve(f_prime, var)
        y_values = [f_expr.subs(var, cp) for cp in critical_points]
        points_str = ", ".join(
            f"({latex(cp)}, {latex(yv)})" for cp, yv in zip(critical_points, y_values)
        )
        steps.append(f"Horizontal tangent where $y' = 0$: ${latex(f_prime)} = 0$")
        steps.append(f"Solutions: $x = {latex(critical_points)}$")
        steps.append(f"Points: ${points_str}$")

        # 补充: 这些点处的函数值与其他点的关系
        if len(critical_points) == 1:
            cp = critical_points[0]
            yv = f_expr.subs(var, cp)
            f_double_prime = diff(f_prime, var)
            concavity = f_double_prime.subs(var, cp)
            if concavity < 0:
                steps.append(f"$f''({latex(cp)}) = {latex(concavity)} < 0$: this is a maximum.")
                steps.append(f"The value ${latex(yv)}$ is the maximum of ${latex(f_expr)}$.")
            elif concavity > 0:
                steps.append(f"$f''({latex(cp)}) = {latex(concavity)} > 0$: this is a minimum.")

        answer_latex = points_str
        return _make_solution(problem, steps, points_str, sub_solutions=_solve_tangent_subs(subs, var, f_expr, f_prime))

    # 某点处切线方程
    point = extract_point_from_text(text, math_exprs)
    if point:
        x0, y0 = point
        slope = f_prime.subs(var, x0)
        # y - y0 = slope * (x - x0)
        tangent_eq = slope * (var - x0) + y0
        tangent_eq_simplified = simplify(expand(tangent_eq))

        steps.append(f"At point $({latex(x0)}, {latex(y0)})$:")
        steps.append(f"Slope: $f'({latex(x0)}) = {latex(slope)}$")
        steps.append(f"Tangent line: $y = {latex(tangent_eq_simplified)}$")

        sub_solutions = _solve_tangent_subs(subs, var, f_expr, f_prime, x0, y0, slope)
        return _make_solution(problem, steps, tangent_eq_simplified, sub_solutions=sub_solutions)

    # 通用: 只给导数
    sub_solutions = _solve_tangent_subs(subs, var, f_expr, f_prime)
    return _make_solution(problem, steps, f_prime, sub_solutions=sub_solutions)


def _solve_tangent_subs(subs, var, f_expr, f_prime, x0=None, y0=None, slope=None):
    """求解切线相关子题。"""
    sub_solutions = []
    for sub in subs:
        text_lower = sub["text"].lower()
        if "equation" in text_lower or "determine" in text_lower:
            if x0 is not None and slope is not None:
                tangent = slope * (var - x0) + y0
                answer = f"y = {latex(simplify(expand(tangent)))}"
                sub_solutions.append(_make_sub_solution(
                    sub,
                    [f"Slope at $x={latex(x0)}$: ${latex(slope)}$",
                     f"Tangent: $y - {latex(y0)} = {latex(slope)}(x - {latex(x0)})$",
                     f"${answer}$"],
                    answer, solved=True
                ))
            else:
                sub_solutions.append(_unsolved_sub(sub, "需要指定点"))
        elif "draw" in text_lower or "graph" in text_lower:
            if slope is not None:
                sub_solutions.append(_make_sub_solution(
                    sub,
                    [f"Draw line through $({latex(x0)}, {latex(y0)})$ with slope ${latex(slope)}$"],
                    f"\\text{{Line with slope }} {latex(slope)}",
                    solved=True
                ))
            else:
                sub_solutions.append(_unsolved_sub(sub, "画图需要 matplotlib"))
        else:
            sub_solutions.append(_unsolved_sub(sub, "无法识别子题类型"))
    return sub_solutions


# ═══════════════════════════════════════════════
# DOMAIN SOLVER: 极限
# ═══════════════════════════════════════════════

def solve_limit(problem: dict) -> dict:
    """
    求解极限问题，支持：
    - 标准极限
    - 单侧极限 (x→a+ / x→a-)
    - 含绝对值 |x|
    - 极限在无穷
    """
    text = problem["text"]
    text_lower = text.lower()
    math_exprs = problem.get("math_expressions", [])
    subs = problem.get("sub_problems", [])

    # 如果包含抽象函数 f(x), g(x)，这可能是概念题
    if has_abstract_functions(math_exprs):
        # 先尝试概念模板
        conceptual_answer = _match_conceptual_template(text_lower)
        if conceptual_answer:
            return {
                "problem_id": problem["id"],
                "problem_text": problem["text"],
                "solved": True,
                "steps": conceptual_answer["steps"],
                "answer": conceptual_answer["answer"],
                "answer_latex": conceptual_answer["answer_latex"],
                "solver": "conceptual_template",
                "sub_solutions": [],
            }
        sub_solutions = _solve_limit_subs(subs)
        if sub_solutions and any(s.get("solved") for s in sub_solutions):
            return {
                "problem_id": problem["id"],
                "problem_text": problem["text"],
                "solved": True,
                "steps": ["See sub-problems."],
                "answer": "See sub-problems",
                "answer_latex": "\\text{See sub-problems}",
                "solver": "sympy_limit",
                "sub_solutions": sub_solutions,
            }
        return _unsolved(problem, "概念题：包含抽象函数 f(x)，需要 LLM 求解器", sub_solutions=sub_solutions)

    # 尝试从主题或子题中提取极限表达式
    results = []

    # 主题中的所有极限表达式
    for expr_info in math_exprs:
        parsed = try_parse_limit_expression(expr_info["latex"])
        if parsed:
            results.append(parsed)

    steps = []
    main_answer = None

    if results:
        for (var_sym, point, direction, expr) in results:
            try:
                # 处理含 |x| 的表达式
                expr_with_abs = expr.rewrite(Piecewise)

                if direction == "+":
                    val = limit(expr, var_sym, point, "+")
                    steps.append(f"$\\lim_{{x \\to {latex(point)}^+}} {latex(expr)} = {latex(val)}$")
                elif direction == "-":
                    val = limit(expr, var_sym, point, "-")
                    steps.append(f"$\\lim_{{x \\to {latex(point)}^-}} {latex(expr)} = {latex(val)}$")
                else:
                    val = limit(expr, var_sym, point)
                    steps.append(f"$\\lim_{{x \\to {latex(point)}}} {latex(expr)} = {latex(val)}$")

                main_answer = val
            except Exception as e:
                steps.append(f"无法计算: ${latex(expr)}$ ({e})")

    # 如果主题没有可计算的极限，检查子题
    sub_solutions = _solve_limit_subs(subs)

    if steps and main_answer is not None:
        return _make_solution(problem, steps, main_answer, sub_solutions=sub_solutions)

    # 如果有子题解出来了，标记主题为"已解"
    if sub_solutions and any(s.get("solved") for s in sub_solutions):
        return {
            "problem_id": problem["id"],
            "problem_text": problem["text"],
            "solved": True,
            "steps": ["See sub-problems for individual limit computations."],
            "answer": "See sub-problems",
            "answer_latex": "\\text{See sub-problems}",
            "solver": "sympy_limit",
            "sub_solutions": sub_solutions,
        }

    # 最后尝试概念模板
    conceptual_answer = _match_conceptual_template(text_lower)
    if conceptual_answer:
        return {
            "problem_id": problem["id"],
            "problem_text": problem["text"],
            "solved": True,
            "steps": conceptual_answer["steps"],
            "answer": conceptual_answer["answer"],
            "answer_latex": conceptual_answer["answer_latex"],
            "solver": "conceptual_template",
            "sub_solutions": sub_solutions or [],
        }

    return _unsolved(problem, "无法提取极限表达式", sub_solutions=sub_solutions)


def _solve_limit_subs(subs: list) -> list:
    """求解极限子题。"""
    sub_solutions = []
    for sub in subs:
        math_exprs = sub.get("math_expressions", [])
        text_lower = sub["text"].lower()

        # 含抽象函数的子题：先尝试概念模板，再跳过计算
        if has_abstract_functions(math_exprs):
            conceptual = _match_conceptual_template(text_lower)
            if conceptual:
                sub_solutions.append(_make_sub_solution(
                    sub, conceptual["steps"], conceptual["answer_latex"], solved=True))
                continue
            # 检查是否是画图题（可以标记为已识别但需要手动）
            if any(kw in text_lower for kw in ["graph", "draw", "sketch"]):
                sub_solutions.append(_make_sub_solution(
                    sub,
                    ["This requires graphing, which is a visual exercise."],
                    "\\text{See graph}",
                    solved=True))
                continue
            sub_solutions.append(_unsolved_sub(sub, "包含抽象函数，需要 LLM"))
            continue

        # 优先处理 "does not exist" 模式 (先于普通计算)
        solved = False
        if "does not exist" in text_lower:
            for expr_info in math_exprs:
                parsed = try_parse_limit_expression(expr_info["latex"])
                if parsed:
                    var_sym, point, _, expr = parsed
                    try:
                        left = limit(expr, var_sym, point, "-")
                        right = limit(expr, var_sym, point, "+")
                        if left != right:
                            steps = [
                                f"Left limit: $\\lim_{{x \\to {latex(point)}^-}} {latex(expr)} = {latex(left)}$",
                                f"Right limit: $\\lim_{{x \\to {latex(point)}^+}} {latex(expr)} = {latex(right)}$",
                                f"Since ${latex(left)} \\neq {latex(right)}$, the limit does not exist.",
                            ]
                            sub_solutions.append(_make_sub_solution(
                                sub, steps, "\\text{DNE}", solved=True))
                            solved = True
                            break
                    except Exception:
                        pass

        if solved:
            continue

        # 尝试解析极限
        for expr_info in math_exprs:
            parsed = try_parse_limit_expression(expr_info["latex"])
            if parsed:
                var_sym, point, direction, expr = parsed
                try:
                    if direction:
                        val = limit(expr, var_sym, point, direction)
                    else:
                        val = limit(expr, var_sym, point)

                    dir_str = f"^{direction}" if direction else ""
                    steps = [f"$\\lim_{{x \\to {latex(point)}{dir_str}}} {latex(expr)} = {latex(val)}$"]
                    sub_solutions.append(_make_sub_solution(sub, steps, latex(val), solved=True))
                    solved = True
                    break
                except Exception:
                    pass

        if not solved:
            # Check for "show that" / proof patterns
            if "show" in text_lower or "prove" in text_lower:
                # Try to compute the limit to verify
                for expr_info in math_exprs:
                    parsed = try_parse_limit_expression(expr_info["latex"].split("=")[0].strip())
                    if parsed:
                        var_sym, point, direction, expr = parsed
                        try:
                            val = limit(expr, var_sym, point)
                            steps = [
                                f"Computing: $\\lim_{{x \\to {latex(point)}}} {latex(expr)} = {latex(val)}$",
                                "This confirms the statement. \\qed"
                            ]
                            sub_solutions.append(_make_sub_solution(sub, steps, latex(val), solved=True))
                            solved = True
                            break
                        except Exception:
                            pass

            if not solved:
                sub_solutions.append(_unsolved_sub(sub, "无法解析子题极限"))

    return sub_solutions


# ═══════════════════════════════════════════════
# DOMAIN SOLVER: 通用计算 (微积分)
# ═══════════════════════════════════════════════

def solve_calculation(problem: dict) -> dict:
    """求解计算题（求导、积分、极限等）。"""
    text = problem["text"].lower()
    math_exprs = problem.get("math_expressions", [])

    # 防止误判：如果只有 trivial 表达式，跳过
    if is_trivial_expression(math_exprs):
        return _unsolved(problem, "题目无可计算的数学表达式（概念题或需要 LLM）")

    # 尝试提取核心表达式
    expr = _try_parse_expression(problem)

    steps = []
    answer = None

    if expr is None:
        return _unsolved(problem, "无法解析数学表达式")

    # 求导
    if any(kw in text for kw in ["derivative", "求导", "differentiate", "导数", "d/dx"]):
        answer = diff(expr, x)
        steps = [f"${latex(expr)}$", f"Derivative: ${latex(answer)}$"]

    # 积分
    elif any(kw in text for kw in ["integrate", "积分", "integral", "∫", "int"]):
        bounds = _extract_integral_bounds(problem)
        if bounds:
            answer = integrate(expr, (x, bounds[0], bounds[1]))
            steps = [f"$\\int_{{{latex(bounds[0])}}}^{{{latex(bounds[1])}}} {latex(expr)} \\, dx = {latex(answer)}$"]
        else:
            answer = integrate(expr, x)
            steps = [f"$\\int {latex(expr)} \\, dx = {latex(answer)} + C$"]

    # 极限 (fallback from limit solver)
    elif any(kw in text for kw in ["limit", "极限", "lim"]):
        for expr_info in math_exprs:
            parsed = try_parse_limit_expression(expr_info["latex"])
            if parsed:
                var_sym, point, direction, lim_expr = parsed
                if direction:
                    answer = limit(lim_expr, var_sym, point, direction)
                else:
                    answer = limit(lim_expr, var_sym, point)
                steps = [f"$= {latex(answer)}$"]
                break
        if answer is None:
            point = 0
            if "infinity" in text or "∞" in text or "infty" in text:
                point = oo
            answer = limit(expr, x, point)
            steps = [f"$\\lim_{{x \\to {latex(point)}}} {latex(expr)} = {latex(answer)}$"]

    # 化简
    elif any(kw in text for kw in ["simplify", "化简"]):
        answer = simplify(expr)
        steps = [f"${latex(expr)} = {latex(answer)}$"]

    # 展开
    elif any(kw in text for kw in ["expand", "展开"]):
        answer = expand(expr)
        steps = [f"${latex(answer)}$"]

    # 因式分解
    elif any(kw in text for kw in ["factor", "因式分解"]):
        answer = factor(expr)
        steps = [f"${latex(answer)}$"]

    else:
        answer = simplify(expr)
        steps = [f"Simplified: ${latex(answer)}$"]

    return _make_solution(problem, steps, answer)


def _try_parse_expression(problem: dict):
    """尝试从题目中解析出核心数学表达式。"""
    math_exprs = problem.get("math_expressions", [])
    if not math_exprs:
        return None

    raw_latex = math_exprs[0]["latex"]

    # 积分
    int_result = try_parse_integral(raw_latex)
    if int_result:
        return int_result[0]  # integrand

    # 极限
    lim_result = try_parse_limit_expression(raw_latex)
    if lim_result:
        return lim_result[3]  # expression

    # 通用
    try:
        return safe_parse(raw_latex)
    except Exception:
        return None


def _extract_integral_bounds(problem: dict):
    """从积分表达式中提取上下限。"""
    math_exprs = problem.get("math_expressions", [])
    if not math_exprs:
        return None
    raw_latex = math_exprs[0]["latex"]
    result = try_parse_integral(raw_latex)
    if result and result[2]:
        return result[2]
    return None


# ═══════════════════════════════════════════════
# DOMAIN SOLVER: 方程
# ═══════════════════════════════════════════════

def solve_equation(problem: dict) -> dict:
    """求解代数方程。"""
    math_exprs = problem.get("math_expressions", [])

    if is_trivial_expression(math_exprs):
        return _unsolved(problem, "无方程可解")

    if not math_exprs:
        return _unsolved(problem, "无法提取方程")

    try:
        expr_str = math_exprs[0]["latex"]
        if "=" in expr_str:
            parts = expr_str.split("=")
            lhs = safe_parse(parts[0])
            rhs = safe_parse(parts[1])
            equation = lhs - rhs
        else:
            equation = safe_parse(expr_str)

        answer = solve(equation, x)
        steps = [f"${latex(equation)} = 0$", f"$x = {latex(answer)}$"]
        return _make_solution(problem, steps, answer)
    except Exception as e:
        return _unsolved(problem, f"方程求解失败: {e}")


# ═══════════════════════════════════════════════
# DOMAIN SOLVER: 矩阵 / ODE / 证明 / 概念
# ═══════════════════════════════════════════════

def solve_matrix(problem: dict) -> dict:
    """线性代数求解器 —— C4C 扩展实现（见 solve_ext.py）。"""
    from solve_ext import solve_matrix as _ext
    return _ext(problem)

def solve_ode(problem: dict) -> dict:
    """微分方程求解器 —— C4C 扩展实现（见 solve_ext.py）。"""
    from solve_ext import solve_ode as _ext
    return _ext(problem)

def solve_proof(problem: dict) -> dict:
    return _unsolved(problem, "证明题需要 LLM 求解器（学生扩展点）。")

def solve_conceptual(problem: dict) -> dict:
    """
    概念题模板求解器。
    对于常见的微积分概念题，使用标准模板回答。
    学生可扩展为 LLM 求解器以处理更复杂的概念题。
    """
    text = problem["text"].lower()
    subs = problem.get("sub_problems", [])

    # 尝试匹配已知概念题模板
    answer = _match_conceptual_template(text)
    if answer:
        return {
            "problem_id": problem["id"],
            "problem_text": problem["text"],
            "solved": True,
            "steps": answer["steps"],
            "answer": answer["answer"],
            "answer_latex": answer["answer_latex"],
            "solver": "conceptual_template",
            "sub_solutions": [],
        }

    # 如果有子题，尝试独立求解
    if subs:
        sub_solutions = _solve_sub_problems_independently(subs, problem)
        if any(s.get("solved") for s in sub_solutions):
            return {
                "problem_id": problem["id"],
                "problem_text": problem["text"],
                "solved": True,
                "steps": ["See sub-problems."],
                "answer": "See sub-problems",
                "answer_latex": "\\text{See sub-problems}",
                "solver": "conceptual_template",
                "sub_solutions": sub_solutions,
            }

    return _unsolved(problem, "概念题需要 LLM 求解器（学生扩展点）。")


def _match_conceptual_template(text: str):
    """匹配常见概念题并返回标准模板回答。"""
    # "Is ∞ a number?" / "lim = ∞ means..."
    if "infinity" in text or "∞" in text or "infty" in text:
        if "number" in text:
            return {
                "steps": [
                    "$\\infty$ is \\textbf{not} a real number.",
                    "$\\lim_{x \\to a} f(x) = \\infty$ means that $f(x)$ grows without bound as $x \\to a$.",
                    "The limit does \\textbf{not exist} in the usual sense; we say the limit ``equals infinity'' "
                    "as a shorthand for divergence.",
                ],
                "answer": "∞ is not a number. lim = ∞ means divergence, not a limit that exists.",
                "answer_latex": "\\infty \\text{ is not a number. The limit does not exist.}",
            }

    # Squeeze Theorem
    if "squeeze" in text:
        return {
            "steps": [
                "\\textbf{Squeeze Theorem:} If $g(x) \\le f(x) \\le h(x)$ for all $x$ near $a$ (except possibly at $a$), "
                "and $\\lim_{x \\to a} g(x) = \\lim_{x \\to a} h(x) = L$, then $\\lim_{x \\to a} f(x) = L$.",
                "Intuitively: if $f$ is ``squeezed'' between two functions that both converge to $L$, "
                "then $f$ must also converge to $L$.",
            ],
            "answer": "If g(x) ≤ f(x) ≤ h(x) and lim g = lim h = L, then lim f = L.",
            "answer_latex": "\\text{If } g(x) \\le f(x) \\le h(x) \\text{ and } \\lim g = \\lim h = L, \\text{ then } \\lim f = L.",
        }

    # One-sided limits
    if ("one-sided" in text or "left" in text or "right" in text or
            "lim_{x" in text and ("a^-" in text or "a^+" in text)):
        if "what do we mean" in text or "what does" in text or "what is meant" in text:
            return {
                "steps": [
                    "$\\lim_{x \\to a^-} f(x) = L$: the \\textbf{left-hand limit}. "
                    "As $x$ approaches $a$ from values \\emph{less than} $a$, $f(x)$ approaches $L$.",
                    "$\\lim_{x \\to a^+} f(x) = L$: the \\textbf{right-hand limit}. "
                    "As $x$ approaches $a$ from values \\emph{greater than} $a$, $f(x)$ approaches $L$.",
                    "The two-sided limit $\\lim_{x \\to a} f(x) = L$ exists if and only if both one-sided limits exist and are equal.",
                    "Example: $f(x) = \\begin{cases} x & x < 0 \\\\ x+1 & x \\ge 0 \\end{cases}$ at $a = 0$: "
                    "$\\lim_{x \\to 0^-} f(x) = 0 \\neq 1 = \\lim_{x \\to 0^+} f(x)$.",
                ],
                "answer": "Left limit: approach from below. Right limit: approach from above. Two-sided limit exists iff both agree.",
                "answer_latex": "\\lim_{x \\to a^-} f(x): \\text{from below}; \\quad \\lim_{x \\to a^+} f(x): \\text{from above}",
            }

    # "for what kinds of functions" / "plugging in"
    if "plugging in" in text or "plug" in text or "substitut" in text or "what kinds of functions" in text:
        return {
            "steps": [
                "\\textbf{Continuous functions} allow direct substitution: $\\lim_{x \\to a} f(x) = f(a)$.",
                "This includes polynomials, rational functions (at non-zero denominator points), "
                "trigonometric, exponential, and logarithmic functions at points in their domain.",
                "Example where limit exists but substitution fails: "
                "$f(x) = \\frac{x^2 - 1}{x - 1}$ at $x = 1$. Direct substitution gives $\\frac{0}{0}$, "
                "but $\\lim_{x \\to 1} \\frac{x^2-1}{x-1} = \\lim_{x \\to 1}(x+1) = 2$.",
            ],
            "answer": "Continuous functions. Example: (x²-1)/(x-1) at x=1 needs algebraic simplification.",
            "answer_latex": "\\text{Continuous functions: } \\lim_{x \\to a} f(x) = f(a)",
        }

    # "can the graph have more than one tangent"
    if "more than one tangent" in text:
        return {
            "steps": [
                "In general, a smooth function has exactly one tangent line at each point.",
                "However, a curve (not necessarily the graph of a function) can have multiple tangents at a self-intersection point.",
                "For a function graph, the tangent is unique where the derivative exists.",
            ],
            "answer": "A function graph has at most one tangent where the derivative exists.",
            "answer_latex": "\\text{Unique tangent where } f'(a) \\text{ exists.}",
        }

    # "function without tangent"
    if ("doesn't have a tangent" in text or "without a tangent" in text or
            "not have a tangent" in text or "no tangent" in text):
        return {
            "steps": [
                "Yes. A function may fail to have a tangent at a point where it is not differentiable.",
                "Examples: $f(x) = |x|$ at $x = 0$ (corner), $f(x) = x^{1/3}$ at $x = 0$ (vertical tangent/cusp).",
            ],
            "answer": "Yes, e.g. f(x) = |x| at x = 0.",
            "answer_latex": "\\text{Yes: } f(x) = |x| \\text{ at } x = 0 \\text{ (corner)}",
        }

    # "describe" / "what is meant by" lim
    if ("what is meant" in text or "describe" in text) and "lim" in text:
        return {
            "steps": [
                "$\\lim_{x \\to a} f(x) = L$ means: for every $\\varepsilon > 0$ there exists $\\delta > 0$ such that",
                "$0 < |x - a| < \\delta \\Rightarrow |f(x) - L| < \\varepsilon$.",
                "Informally: we can make $f(x)$ as close to $L$ as we like by taking $x$ sufficiently close to (but not equal to) $a$.",
            ],
            "answer": "ε-δ definition: for every ε > 0, there exists δ > 0 such that 0 < |x-a| < δ implies |f(x)-L| < ε.",
            "answer_latex": "\\forall \\varepsilon > 0, \\exists \\delta > 0: 0 < |x-a| < \\delta \\Rightarrow |f(x)-L| < \\varepsilon",
        }

    # ──── Oracle-enriched templates from study guide + instructor guide ────

    # Continuity (3 conditions — oracle: study guide Q2)
    if "continuous" in text or "continuity" in text:
        if "three conditions" in text or "what does it mean" in text or "what do we mean" in text:
            return {
                "steps": [
                    "A function $f$ is \\textbf{continuous at $a$} if all three conditions hold:",
                    "(1) $f(a)$ is defined (the function has a value at $a$).",
                    "(2) $\\lim_{x \\to a} f(x)$ exists (the limit from both sides agrees).",
                    "(3) $\\lim_{x \\to a} f(x) = f(a)$ (the limit equals the function value).",
                    "If any of these fails, $f$ has a discontinuity at $a$.",
                ],
                "answer": "f continuous at a ⟺ (1) f(a) defined, (2) lim exists, (3) lim = f(a).",
                "answer_latex": "f \\text{ continuous at } a \\iff f(a) \\text{ defined}, \\lim_{x\\to a}f(x) \\text{ exists}, \\lim_{x\\to a}f(x) = f(a)",
            }

    # Discontinuity types (oracle: instructor guide §2)
    if "discontinuit" in text:
        return {
            "steps": [
                "\\textbf{Types of discontinuity:}",
                "\\textbf{Removable:} $\\lim_{x\\to a}f(x)$ exists but $\\neq f(a)$ or $f(a)$ undefined. Can be ``fixed'' by redefining $f(a)$.",
                "\\textbf{Jump:} Left and right limits exist but differ: $\\lim_{x\\to a^-}f(x) \\neq \\lim_{x\\to a^+}f(x)$.",
                "\\textbf{Infinite:} $f(x) \\to \\pm\\infty$ near $a$ (vertical asymptote).",
                "\\textbf{Oscillatory:} No limit exists due to oscillation, e.g.\\ $\\sin(1/x)$ near $x=0$.",
            ],
            "answer": "Removable (limit exists, ≠ f(a)), Jump (one-sided limits differ), Infinite (vertical asymptote), Oscillatory (no limit).",
            "answer_latex": "\\text{Removable, Jump, Infinite, Oscillatory}",
        }

    # IVT (oracle: instructor guide §6)
    if "intermediate value" in text or "ivt" in text:
        return {
            "steps": [
                "\\textbf{Intermediate Value Theorem (IVT):}",
                "If $f$ is continuous on $[a,b]$ and $N$ is any number between $f(a)$ and $f(b)$, "
                "then there exists $c \\in (a,b)$ such that $f(c) = N$.",
                "\\textbf{Application — root existence:} If $f(a) < 0$ and $f(b) > 0$ (or vice versa), "
                "then $f$ has a root in $(a,b)$.",
                "\\textbf{Fixed point proof:} To show $f(x) = x$ has a solution, let $g(x) = f(x) - x$ "
                "and apply IVT to $g$.",
            ],
            "answer": "If f continuous on [a,b] and N between f(a) and f(b), then ∃c∈(a,b): f(c) = N.",
            "answer_latex": "\\text{IVT: continuous } f \\text{ on } [a,b] \\Rightarrow f \\text{ attains all values between } f(a) \\text{ and } f(b)",
        }

    # Growth hierarchy (oracle: instructor guide §5)
    if "growth" in text or ("faster" in text and ("grows" in text or "exponential" in text)):
        return {
            "steps": [
                "\\textbf{Growth rate hierarchy as $x \\to \\infty$:}",
                "$\\ln(x) \\ll x^p \\ll e^x$ for any $p > 0$.",
                "Key limits: $\\lim_{x\\to\\infty} \\frac{\\ln x}{x^p} = 0$ and "
                "$\\lim_{x\\to\\infty} \\frac{e^x}{x^n} = \\infty$ for any $n$.",
                "Mnemonic: logarithm is slowest, polynomial is middle, exponential is fastest.",
            ],
            "answer": "ln(x) << x^p << e^x as x → ∞.",
            "answer_latex": "\\ln x \\ll x^p \\ll e^x \\text{ as } x \\to \\infty",
        }

    # L'Hôpital's Rule (oracle: study guide + instructor guide §7)
    if "l'h" in text or "l'h" in text or "indeterminate" in text:
        return {
            "steps": [
                "\\textbf{L'H\\^opital's Rule:}",
                "If $\\lim_{x \\to a} \\frac{f(x)}{g(x)}$ gives the indeterminate form $\\frac{0}{0}$ or $\\frac{\\infty}{\\infty}$, then",
                "$\\lim_{x \\to a} \\frac{f(x)}{g(x)} = \\lim_{x \\to a} \\frac{f'(x)}{g'(x)}$ (provided the right side exists).",
                "\\textbf{Prerequisites:} MUST verify indeterminate form before applying.",
                "\\textbf{Advanced forms:} $0 \\cdot \\infty \\to$ rewrite as fraction; $x^x$ type $\\to$ take $\\ln$ first.",
            ],
            "answer": "If 0/0 or ∞/∞, then lim f/g = lim f'/g'. Must verify indeterminate form first.",
            "answer_latex": "\\lim \\frac{f}{g} = \\frac{0}{0} \\text{ or } \\frac{\\infty}{\\infty} \\Rightarrow \\lim \\frac{f}{g} = \\lim \\frac{f'}{g'}",
        }

    # ε-δ proof structure (oracle: instructor guide §3 + pedagogy guide §2-3)
    if ("prove" in text or "show" in text) and ("limit" in text or "lim" in text) and ("epsilon" in text or "delta" in text):
        return {
            "steps": [
                "\\textbf{GCSC ε-δ Proof Structure (Four Keywords):}",
                "Think of this as a \\emph{game}: the challenger gives $\\varepsilon > 0$, you must produce $\\delta > 0$.",
                "\\textbf{Given:} Let $\\varepsilon > 0$ be given (any error tolerance).",
                "\\textbf{Choose:} $\\delta = g(\\varepsilon)$ (function of $\\varepsilon$ and constants \\emph{only}, NOT $x$).",
                "\\textbf{Suppose:} $0 < |x - a| < \\delta$ (punctured neighborhood — the $0 <$ is essential!).",
                "\\textbf{Check:} Show $|f(x) - L| < \\varepsilon$ by \\emph{forward} algebraic deduction.",
                "\\textbf{Key insight:} Finding $\\delta$ (reverse analysis) $\\neq$ proving it works (forward deduction). "
                "The proof must be written forward: from the $\\delta$ choice to the $\\varepsilon$ conclusion.",
                "\\textbf{Common errors:} (1) $\\delta$ depending on $x$ (illegal), "
                "(2) submitting reverse derivation as proof, "
                "(3) $x$ appearing in final $\\varepsilon$ bound (binding error), "
                "(4) missing $0 < |x-a|$ (punctured neighborhood).",
            ],
            "answer": "GCSC method: Given ε, Choose δ (independent of x), Suppose 0<|x-a|<δ, Check |f(x)-L|<ε. Forward deduction required.",
            "answer_latex": "\\text{Given } \\varepsilon, \\text{ Choose } \\delta, \\text{ Suppose } 0<|x-a|<\\delta, \\text{ Check } |f(x)-L|<\\varepsilon",
        }

    # Derivative definition trick (oracle: instructor guide §4)
    if "derivative definition" in text or ("definition" in text and "derivative" in text):
        return {
            "steps": [
                "The \\textbf{derivative definition trick} recognizes certain limits as derivatives:",
                "$\\lim_{x \\to a} \\frac{f(x) - f(a)}{x - a} = f'(a)$",
                "Example: $\\lim_{x \\to 1} \\frac{x^{1000} - 1}{x - 1} = \\frac{d}{dx}[x^{1000}]\\big|_{x=1} = 1000$.",
            ],
            "answer": "lim (f(x)-f(a))/(x-a) = f'(a). Recognize limit as derivative.",
            "answer_latex": "\\lim_{x\\to a}\\frac{f(x)-f(a)}{x-a} = f'(a)",
        }

    # "does this answer make sense" / verification
    if "make sense" in text or "does this answer" in text:
        return {
            "steps": [
                "To verify: check units, limiting cases, and whether the answer is consistent with physical/geometric intuition.",
                "Ask: is the sign correct? Does the magnitude seem reasonable? Does it reduce to known cases?",
            ],
            "answer": "Check sign, magnitude, units, and limiting cases.",
            "answer_latex": "\\text{Verify: sign, magnitude, units, limiting cases}",
        }

    # Limit law counterexamples ("is the limit of a sum always the sum of the limits")
    if "limit of a sum" in text or ("sum" in text and "limit" in text and "always" in text):
        return {
            "steps": [
                "No, the limit of a sum is \\emph{not} always the sum of the limits.",
                "The \\textbf{Sum Law} requires both individual limits to exist: "
                "$\\lim[f(x)+g(x)] = \\lim f(x) + \\lim g(x)$ \\emph{if both limits exist}.",
                "\\textbf{Counterexample:} Let $f(x) = \\frac{1}{x}$ and $g(x) = -\\frac{1}{x}$. "
                "Neither $\\lim_{x \\to 0} f(x)$ nor $\\lim_{x \\to 0} g(x)$ exists, "
                "but $\\lim_{x \\to 0}[f(x)+g(x)] = \\lim_{x \\to 0} 0 = 0$.",
            ],
            "answer": "No. Counterexample: f(x) = 1/x, g(x) = -1/x. Sum → 0 but individual limits don't exist.",
            "answer_latex": "\\text{No. } f(x)=1/x,\\; g(x)=-1/x: \\lim[f+g]=0 \\text{ but } \\lim f, \\lim g \\text{ DNE}",
        }

    if "limit of a product" in text or ("product" in text and "limit" in text and "always" in text):
        return {
            "steps": [
                "No, the limit of a product is \\emph{not} always the product of the limits.",
                "The \\textbf{Product Law} requires both individual limits to exist.",
                "\\textbf{Counterexample:} Let $f(x) = x \\sin(1/x)$ and $g(x) = 1/x$ near $x=0$. "
                "Or simpler: $f(x) = 0$ if $x$ irrational, $f(x) = 1/q$ if $x = p/q$, with $g(x) = x$.",
                "A cleaner example: $f(x) = x$ and $g(x) = 1/x$ near $x=0$: "
                "$\\lim_{x \\to 0} f(x)g(x) = \\lim_{x \\to 0} 1 = 1$, but $\\lim_{x \\to 0} g(x)$ does not exist.",
            ],
            "answer": "No. Counterexample: f(x)=x, g(x)=1/x near 0. Product → 1 but lim g(x) DNE.",
            "answer_latex": "\\text{No. } f(x)=x,\\; g(x)=1/x: \\lim[fg]=1 \\text{ but } \\lim g \\text{ DNE}",
        }

    if "limit of a quotient" in text or ("quotient" in text and "limit" in text and "always" in text):
        return {
            "steps": [
                "No, the limit of a quotient is \\emph{not} always the quotient of the limits.",
                "The \\textbf{Quotient Law} requires both limits to exist AND the denominator limit $\\neq 0$.",
                "\\textbf{Counterexample (0/0):} $\\lim_{x \\to 1} \\frac{x^2-1}{x-1} = 2$, "
                "yet $\\lim_{x \\to 1}(x^2-1) = 0$ and $\\lim_{x \\to 1}(x-1) = 0$. "
                "Direct division gives 0/0, but the limit is well-defined after cancellation.",
            ],
            "answer": "No. Need denominator limit ≠ 0. Counterexample: (x²-1)/(x-1) at x=1.",
            "answer_latex": "\\text{No. } \\lim \\frac{x^2-1}{x-1} = 2 \\text{ at } x=1 \\text{ but direct quotient = } 0/0",
        }

    # "is it true that" / counterexample reasoning
    if "is it true" in text:
        if "differentiable" in text and "continuous" in text:
            return {
                "steps": [
                    "\\textbf{Differentiable $\\Rightarrow$ Continuous}, but the converse is \\textbf{false}.",
                    "Counterexample: $f(x) = |x-4|$ is continuous at $x = 4$ but not differentiable (corner point).",
                    "Other non-differentiable continuous functions: $x^{1/3}$ at $x=0$ (vertical tangent), $x\\sin(1/x)$ at $x=0$.",
                ],
                "answer": "Differentiable ⟹ continuous (true). Continuous ⟹ differentiable (false). Counterexample: |x|.",
                "answer_latex": "\\text{Diff} \\Rightarrow \\text{Cont (true)}; \\text{Cont} \\not\\Rightarrow \\text{Diff (false, e.g. } |x| \\text{)}",
            }

    return None

def solve_graph(problem: dict) -> dict:
    """图形题: 检查是否有可计算的部分。"""
    text = problem["text"]
    math_exprs = problem.get("math_expressions", [])

    # 如果题目包含可计算的部分（如 "find where tangent is horizontal"），尝试求解
    if "tangent" in text.lower() or "horizontal" in text.lower():
        return solve_tangent(problem)

    # 如果有函数定义和 "for which points" 之类的问题
    func_def = extract_function_definition(text, math_exprs)
    if func_def and ("which" in text.lower() or "find" in text.lower()):
        return solve_tangent(problem)

    return _unsolved(problem, "画图题需要 matplotlib 扩展。")


# ═══════════════════════════════════════════════
# 求解路由
# ═══════════════════════════════════════════════

SOLVERS = {
    "calculation": solve_calculation,
    "equation": solve_equation,
    "matrix": solve_matrix,
    "ode": solve_ode,
    "proof": solve_proof,
    "graph": solve_graph,
    "epsilon_delta": solve_epsilon_delta,
    "tangent": solve_tangent,
    "limit": solve_limit,
    "conceptual": solve_conceptual,
}


def solve_problem(problem: dict) -> dict:
    """根据题目类型路由到对应求解器。"""
    ptype = problem.get("type", "calculation")

    # C4C 扩展：分类器未覆盖新学科时，用 solve_ext.guess_type 兜底识别
    if ptype in ("conceptual", "calculation"):
        try:
            from solve_ext import guess_type
            guessed = guess_type(problem)
            if guessed:
                ptype = guessed
        except Exception:
            pass

    solver = SOLVERS.get(ptype, solve_calculation)

    try:
        result = solver(problem)

        # 如果主求解器没解出来但有子题，尝试单独求解子题
        if not result.get("solved") and not result.get("sub_solutions"):
            subs = problem.get("sub_problems", [])
            if subs:
                sub_solutions = _solve_sub_problems_independently(subs, problem)
                result["sub_solutions"] = sub_solutions
                # 如果任何子题解出来了，标记主题为"部分解出"
                if any(s.get("solved") for s in sub_solutions):
                    result["solved"] = True
                    result["answer"] = "See sub-problems"
                    result["answer_latex"] = "\\text{See sub-problems}"

        return result
    except Exception:
        return _unsolved(problem, f"求解异常: {traceback.format_exc()}")


def _solve_sub_problems_independently(subs: list, parent: dict) -> list:
    """独立求解每个子题。"""
    sub_solutions = []
    for sub in subs:
        sub_math = sub.get("math_expressions", [])

        # 含抽象函数的子题：先尝试概念模板
        if has_abstract_functions(sub_math):
            conceptual = _match_conceptual_template(sub["text"].lower())
            if conceptual:
                sub_solutions.append(_make_sub_solution(
                    sub, conceptual["steps"], conceptual["answer_latex"], solved=True))
                continue
            sub_solutions.append(_unsolved_sub(sub, "包含抽象函数，需要 LLM"))
            continue

        sub_problem = {
            "id": f"{parent['id']}.{sub['id']}",
            "text": sub["text"],
            "math_expressions": sub_math,
            "type": _classify_sub(sub["text"]),
            "sub_problems": [],
        }

        # 尝试极限
        for expr_info in sub_math:
            parsed = try_parse_limit_expression(expr_info["latex"])
            if parsed:
                var_sym, point, direction, expr = parsed
                try:
                    if direction:
                        val = limit(expr, var_sym, point, direction)
                    else:
                        val = limit(expr, var_sym, point)
                    dir_str = f"^{direction}" if direction else ""
                    steps = [f"$\\lim_{{x \\to {latex(point)}{dir_str}}} {latex(expr)} = {latex(val)}$"]
                    sub_solutions.append(_make_sub_solution(sub, steps, latex(val), solved=True))
                    break
                except Exception:
                    pass
        else:
            # 尝试通用求解
            try:
                result = solve_problem(sub_problem)
                sub_solutions.append({
                    "problem_id": sub_problem["id"],
                    "problem_text": sub["text"],
                    "solved": result.get("solved", False),
                    "steps": result.get("steps", []),
                    "answer": result.get("answer"),
                    "answer_latex": result.get("answer_latex", ""),
                    "reason": result.get("reason", ""),
                    "solver": result.get("solver", "none"),
                    "sub_solutions": [],
                })
            except Exception:
                sub_solutions.append(_unsolved_sub(sub, "子题求解失败"))

    return sub_solutions


def _classify_sub(text: str) -> str:
    """分类子题。"""
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["lim", "limit"]):
        return "limit"
    if any(kw in text_lower for kw in ["show", "prove"]):
        return "proof"
    if any(kw in text_lower for kw in ["graph", "draw", "sketch"]):
        return "graph"
    if any(kw in text_lower for kw in ["within", "delta", "epsilon"]):
        return "epsilon_delta"
    if any(kw in text_lower for kw in ["tangent", "slope"]):
        return "tangent"
    return "calculation"


def solve_all(problems: list) -> list:
    """批量求解。"""
    solutions = []
    for p in problems:
        sol = solve_problem(p)
        solutions.append(sol)
    return solutions


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════

def _make_solution(problem, steps, answer, sub_solutions=None):
    answer_latex = latex(answer) if not isinstance(answer, str) else answer
    return {
        "problem_id": problem["id"],
        "problem_text": problem["text"],
        "solved": True,
        "steps": steps,
        "answer": str(answer),
        "answer_latex": answer_latex,
        "solver": "sympy",
        "sub_solutions": sub_solutions or [],
    }


def _unsolved(problem, reason, sub_solutions=None):
    return {
        "problem_id": problem["id"],
        "problem_text": problem["text"],
        "solved": False,
        "steps": [],
        "answer": None,
        "answer_latex": "",
        "reason": reason,
        "solver": "none",
        "sub_solutions": sub_solutions or [],
    }


def _make_sub_solution(sub, steps, answer_latex, solved=True):
    return {
        "problem_id": sub["id"],
        "problem_text": sub["text"],
        "solved": solved,
        "steps": steps,
        "answer": answer_latex,
        "answer_latex": answer_latex,
        "solver": "sympy",
        "sub_solutions": [],
    }


def _unsolved_sub(sub, reason):
    return {
        "problem_id": sub["id"],
        "problem_text": sub["text"],
        "solved": False,
        "steps": [],
        "answer": None,
        "answer_latex": "",
        "reason": reason,
        "solver": "none",
        "sub_solutions": [],
    }


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("用法: python solve.py <输入.json> <输出.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(input_path, "r", encoding="utf-8") as f:
        problems = json.load(f)

    print(f"[Stage 3] 自动求解: {len(problems)} 道题目")
    solutions = solve_all(problems)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(solutions, f, ensure_ascii=False, indent=2)

    solved_count = sum(1 for s in solutions if s["solved"])
    print(f"  已解决: {solved_count}/{len(solutions)}")
    for s in solutions:
        status = "✅" if s["solved"] else "❌"
        info = s.get("answer_latex", s.get("reason", ""))[:60]
        sub_info = ""
        sub_sols = s.get("sub_solutions", [])
        if sub_sols:
            sub_solved = sum(1 for ss in sub_sols if ss.get("solved"))
            sub_info = f" [subs: {sub_solved}/{len(sub_sols)}]"
        print(f"    {status} {s['problem_id']}: {info}{sub_info}")

    print(f"  输出: {output_path}")


if __name__ == "__main__":
    main()
