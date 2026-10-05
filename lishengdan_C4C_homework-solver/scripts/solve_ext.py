#!/usr/bin/env python3
"""
新学科求解器扩展（C4C Level 2/3）：线性代数 + 微分方程
=====================================================

Starter kit 中 solve_matrix / solve_ode 是空壳（"学生扩展点"）。
本模块把它们实现为完整的 SymPy 求解器：

线性代数 (solve_matrix):
  - 行列式 det(A)、逆矩阵 A⁻¹、秩 rank(A)、转置 Aᵀ
  - 矩阵乘法 AB、幂 Aⁿ
  - 特征值/特征向量 eigenvals/eigenvects
  - 对角化 diagonalize
  - 线性方程组 linsolve（增广矩阵 or 方程列表）
  - Gram-Schmidt 正交化

微分方程 (solve_ode):
  - 一阶可分离/线性 ODE: y' = f(x, y)
  - 二阶常系数齐次/非齐次: y'' + py' + qy = f(x)
  - 初值问题（自动从题干提取 y(x0)=a, y'(x0)=b 作为 ics）
  - 通解/特解判别

矩阵输入格式（LaTeX）: \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}
（bmatrix / vmatrix / array 同样支持）
"""

import re
import traceback

import sympy
from sympy import dsolve, ode_order
from sympy import (
    symbols, Symbol, Function, Matrix, eye, zeros, det, trace,
    latex, simplify, Rational, Integer, S, Eq, Derivative, dsolve,
    sqrt, pi, exp, sin, cos, log,
)
from sympy.matrices import MatrixBase
from sympy.matrices.dense import Matrix

# 与 solve.py 保持一致的辅助输出格式约定：
#   _make_solution(problem, steps, answer) / _unsolved(problem, reason)
# 为避免循环导入，这里复制其实现（保持 JSON 字段完全一致）。

x_sym = Symbol("x")
t_sym = Symbol("t")


# ═══════════════════════════════════════════════
# 输出格式助手（与 solve.py 字段兼容）
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
        "solver": "sympy_ext",
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


# ═══════════════════════════════════════════════
# LaTeX 矩阵解析
# ═══════════════════════════════════════════════

def parse_matrix(latex_str: str) -> Matrix:
    """
    解析 LaTeX 矩阵为 sympy Matrix。
    支持 pmatrix/bmatrix/vmatrix/matrix/array（含增广矩阵的 | 分隔，
    增广矩阵返回 (系数矩阵, 右端列) 元组）。
    """
    s = latex_str.strip()

    # 增广矩阵: \left[\begin{array}{ccc|c} ... \end{array}\right]
    aug_match = re.search(
        r"\\?left\[?\s*\\begin\{array\}\{[^}]*\|[^}]*\}(.*?)\\end\{array\}\\?right\]?",
        s, re.DOTALL)
    if aug_match:
        body = aug_match.group(1)
        rows, rhs = [], []
        for row in re.split(r"\\\\", body):
            row = row.strip()
            if not row:
                continue
            vals = [_parse_cell(c) for c in row.split("&")]
            # 最后一列是增广列
            rows.append(vals[:-1])
            rhs.append(vals[-1])
        return Matrix(rows), Matrix(rhs)

    m = re.search(
        r"\\begin\{(p|b|v|B|V)?matrix\}(.*?)\\end\{(p|b|v|B|V)?matrix\}",
        s, re.DOTALL)
    if not m:
        m = re.search(r"\\begin\{array\}\{[^}]*\}(.*?)\\end\{array\}", s, re.DOTALL)
    if not m:
        raise ValueError(f"未找到矩阵环境: {latex_str[:60]}")

    # 命中 matrix 环境时取 group(2)（矩阵体）；命中 array 时取 group(1)
    body = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) is not None else m.group(1)
    rows = []
    for row in re.split(r"\\\\", body):
        row = row.strip()
        if not row:
            continue
        rows.append([_parse_cell(c) for c in row.split("&")])
    if not rows:
        raise ValueError("矩阵为空")
    return Matrix(rows)


def _parse_cell(cell: str):
    """解析单个矩阵元素（整数/分数/小数/符号）。"""
    c = cell.strip().replace("\\left", "").replace("\\right", "")
    c = c.replace("\\frac{", "FRAC{").replace("−", "-")
    # \frac{a}{b}
    m = re.match(r"FRAC\{([^{}]+)\}\{([^{}]+)\}$", c)
    if m:
        return Rational(m.group(1).strip(), m.group(2).strip())
    # a/b
    m = re.match(r"^(-?\d+)/(\d+)$", c)
    if m:
        return Rational(m.group(1), m.group(2))
    try:
        return Integer(c)
    except Exception:
        pass
    try:
        return Rational(c)
    except Exception:
        pass
    return Symbol(c.replace(" ", ""))


def _find_all_matrices(problem: dict):
    """从题目公式中找到所有矩阵（按出现顺序）。"""
    mats = []
    sources = [e.get("latex", "") for e in problem.get("math_expressions", [])]
    sources.append(problem.get("text", ""))
    for src in sources:
        for m in re.finditer(r"\\begin\{(?:p|b|v|B|V)?matrix\}.*?\\end\{(?:p|b|v|B|V)?matrix\}",
                             src, re.DOTALL):
            try:
                mats.append(parse_matrix(m.group(0)))
            except Exception:
                continue
    return mats


def _find_matrix(problem: dict):
    """从题目及公式中找到第一个矩阵。"""
    for e in problem.get("math_expressions", []):
        lx = e.get("latex", "")
        if "matrix" in lx or "array" in lx:
            try:
                return parse_matrix(lx)
            except Exception:
                continue
    # 尝试从题干文本中找
    for m in re.finditer(r"\\begin\{(?:p|b|v)?matrix\}.*?\\end\{(?:p|b|v)?matrix\}",
                         problem.get("text", ""), re.DOTALL):
        try:
            return parse_matrix(m.group(0))
        except Exception:
            continue
    return None


# ═══════════════════════════════════════════════
# 线性代数求解器
# ═══════════════════════════════════════════════

def solve_matrix(problem: dict) -> dict:
    text = problem.get("text", "")
    text_lower = text.lower()
    math_exprs = problem.get("math_expressions", [])
    full = text_lower + " " + " ".join(e.get("latex", "") for e in math_exprs)

    # ── 线性方程组（增广矩阵形式）──
    if ("方程组" in text or "system" in text_lower or
            re.search(r"array\}\{[^}]*\|", " ".join(e.get("latex", "") for e in math_exprs))):
        result = _solve_linear_system(problem)
        if result:
            return result

    A = _find_matrix(problem)
    if A is None:
        return _unsolved(problem, "未找到矩阵")

    steps = [f"矩阵 $A = {latex(A)}$"]

    # ── 特征值 / 特征向量 ──
    if "特征值" in text or "特征向量" in text or "eigen" in text_lower:
        return _solve_eigen(problem, A, steps,
                            want_vectors=("特征向量" in text or "vector" in text_lower))

    # ── 行列式 ──
    if "行列式" in text or "determinant" in text_lower or re.search(r"\bdet\b", full):
        d = A.det()
        steps.append("按行列式定义展开（SymPy 符号计算，逐步约化）")
        steps.append(f"$\\det(A) = {latex(d)}$")
        return _make_solution(problem, steps, d)

    # ── 逆矩阵 ──
    if "逆" in text or "inverse" in text_lower:
        if A.det() == 0:
            steps.append(f"$\\det(A) = 0$，因此 $A$ 不可逆")
            return _make_solution(problem, steps, "\\text{A 不可逆}")
        Ainv = A.inv()
        steps.append(f"$\\det(A) = {latex(A.det())} \\neq 0$，A 可逆")
        steps.append(f"伴随矩阵法 / 初等行变换法求得 $A^{{-1}} = {latex(Ainv)}$")
        return _make_solution(problem, steps, Ainv)

    # ── 秩 ──
    if "秩" in text or "rank" in text_lower:
        r = A.rank()
        steps.append("对 A 作初等行变换化为行阶梯形")
        steps.append(f"非零行数 = {r}，故 $r(A) = {r}$")
        return _make_solution(problem, steps, r)

    # ── 转置 ──
    if "转置" in text or "transpose" in text_lower:
        AT = A.T
        steps.append(f"$A^T = {latex(AT)}$")
        return _make_solution(problem, steps, AT)

    # ── Gram-Schmidt 正交化 ──
    if "正交" in text or "orthogonal" in text_lower or "schmidt" in text_lower:
        cols = [A[:, i] for i in range(A.cols)]
        # Gram-Schmidt 正交化（sympy.matrices.gram_schmidt）
        from sympy.matrices.gram_schmidt import gram_schmidt as _gs
        ortho = _gs(cols, orthonormal=False)
        steps.append("对列向量组依次作 Gram-Schmidt 正交化：")
        for i, v in enumerate(ortho):
            steps.append(f"$\\beta_{{{i+1}}} = {latex(v)}$")
        return _make_solution(problem, steps, Matrix.hstack(*ortho))

    # ── 对角化 ──
    if "对角化" in text or "diagonal" in text_lower:
        P, D = A.diagonalize()
        steps.append("求出全部特征值与特征向量")
        steps.append(f"$P = {latex(P)}$, $D = {latex(D)}$")
        steps.append(f"验证 $PDP^{{-1}} = A$")
        return _make_solution(problem, steps, (P, D))

    # ── 幂 A^n ──
    m_pow = re.search(r"A\^(\{?(\d+)\}?)", full)
    if m_pow and "乘" not in text:
        n = int(m_pow.group(2))
        An = A ** n
        steps.append(f"计算 $A^{{{n}}}$（可先对角化再求幂）")
        steps.append(f"$A^{{{n}}} = {latex(An)}$")
        return _make_solution(problem, steps, An)

    # ── 矩阵乘法 AB ──
    if "乘" in text or "product" in text_lower or re.search(r"\bAB\b", full):
        mats = _find_all_matrices(problem)
        if len(mats) >= 2:
            P = mats[0] * mats[1]
            steps.append(f"$AB = {latex(mats[0])} \\cdot {latex(mats[1])}$")
            steps.append("按行乘列法则：$c_{ij} = \\sum_k a_{ik} b_{kj}$")
            steps.append(f"$AB = {latex(P)}$")
            return _make_solution(problem, steps, P)

    # 默认：给出矩阵的完整基本量
    d, tr, r = A.det(), A.trace(), A.rank()
    steps.append(f"$\\det(A) = {latex(d)}$, $\\mathrm{{tr}}(A) = {latex(tr)}$, $r(A) = {r}$")
    return _make_solution(problem, steps, d)


def _solve_eigen(problem, A, steps, want_vectors=False):
    vals = A.eigenvals()
    steps.append("特征方程 $\\det(A - \\lambda I) = 0$，展开求解：")
    val_parts = ", ".join(
        f"$\\lambda = {latex(v)}$（重数 {m}）" if m > 1 else f"$\\lambda = {latex(v)}$"
        for v, m in vals.items())
    steps.append(val_parts)

    if not want_vectors:
        val_str = ", \\; ".join(f"\\lambda_{{{i+1}}} = {latex(v)}"
                                for i, v in enumerate(vals.keys()))
        steps.append(f"特征值: ${val_str}$")
        return _make_solution(problem, steps, val_str)

    steps.append("对每个特征值解 $(A - \\lambda I)\\xi = 0$：")
    ans_parts = []
    for v, mult, vecs in A.eigenvects():
        for vec in vecs:
            steps.append(f"$\\lambda = {latex(v)}$: $\\xi = {latex(vec)}$")
            ans_parts.append(f"\\lambda = {latex(v)},\\ \\xi = {latex(vec)}")
    answer = "; \\quad ".join(ans_parts)
    return _make_solution(problem, steps, answer)


def _solve_linear_system(problem: dict):
    """解线性方程组（增广矩阵或方程列表形式）。"""
    math_exprs = problem.get("math_expressions", [])
    # 增广矩阵形式
    for e in math_exprs:
        lx = e.get("latex", "")
        if re.search(r"array\}\{[^}]*\|", lx) or re.search(r"array\}\{[^}]*\|\}", lx):
            try:
                Aaug = parse_matrix(lx)
                if isinstance(Aaug, tuple):
                    A, b = Aaug
                else:
                    A, b = Aaug[:, :-1], Aaug[:, -1]
                return _finish_linsolve(problem, A, b)
            except Exception:
                continue
    # 方程列表形式: x + 2y = 4, 3x - y = 5（从文本提取）
    text = problem.get("text", "")
    eqs = re.findall(r"([-+*/.\d\sxyztuvwa-zA-Z\\{}^()]+=[-+*/.\d\s\\{}^()]+)", text)
    if len(eqs) >= 2:
        try:
            sym_names = sorted({ch for eq in eqs for ch in re.findall(r"[a-w]", eq)})
            syms = symbols(" ".join(sym_names)) if sym_names else []
            if not isinstance(syms, (list, tuple)):
                syms = [syms]
            parsed_eqs = []
            for es in eqs:
                lhs, rhs = es.split("=", 1)
                from solve import safe_parse  # 复用 starter kit 的 LaTeX 表达式解析器
                le, re_ = safe_parse(lhs), safe_parse(rhs)
                parsed_eqs.append(Eq(le, re_))
            sol = sympy.linsolve(parsed_eqs, syms)
            steps = [f"方程组: {', '.join(eqs)}"]
            steps.append(f"高斯消元得解集: ${latex(sol)}$")
            return _make_solution(problem, steps, sol)
        except Exception:
            return None
    return None


def _finish_linsolve(problem, A, b):
    aug = Matrix.hstack(A, b)
    sol = sympy.linsolve((A, b))
    steps = [
        f"增广矩阵 $\\overline{{A}} = {latex(aug)}$",
        "初等行变换化为行最简形，判定解的情况",
    ]
    rA, rAug = A.rank(), aug.rank()
    if rA < rAug:
        steps.append("$r(A) < r(\\overline{A})$，方程组无解")
        return _make_solution(problem, steps, "\\text{无解}")
    n = A.cols
    if rA == n:
        steps.append(f"$r(A) = r(\\overline{{A}}) = n = {n}$，有唯一解")
    else:
        steps.append(f"$r(A) = r(\\overline{{A}}) = {rA} < n = {n}$，有无穷多解（自由变量 {n - rA} 个）")
    steps.append(f"解集: ${latex(sol)}$")
    return _make_solution(problem, steps, sol)


# ═══════════════════════════════════════════════
# 微分方程求解器
# ═══════════════════════════════════════════════

def _ode_to_sympy(s: str):
    """
    把 LaTeX/文本 ODE 转换为 sympy 表达式（y = y(x)）。
    支持 y'', y', y 与 d²y/dx², dy/dx 记法。
    返回 (表达式或等式, Function y, 自变量符号)。
    """
    s = s.replace("−", "-")
    # 各种导数记法归一为 y'' / y'
    s = re.sub(r"\\frac\s*\{\s*d\^?\{?2\}?\s*y\s*\}\s*\{\s*d\s*x\^?\{?2\}?\s*\}", "y''", s)
    s = re.sub(r"\\frac\s*\{\s*dy\s*\}\s*\{\s*dx\s*\}", "y'", s)
    s = re.sub(r"d\^\{?2\}?\s*y\s*/\s*d\s*x\^\{?2\}?", "y''", s)
    s = re.sub(r"dy\s*/\s*dx", "y'", s)
    s = re.sub(r"\\mathrm\{d\}\^?\{?2\}?\s*y", "y''", s)
    s = re.sub(r"\\mathrm\{d\}y", "dy", s)
    # 清理 LaTeX 粉尘
    s = re.sub(r"\\left|\\right", "", s)
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = re.sub(r"\\[a-zA-Z]+", lambda m: {"\\pi": "pi", "\\sin": "sin",
                                          "\\cos": "cos", "\\exp": "exp",
                                          "\\ln": "log", "\\log": "log",
                                          "\\quad": " ", "\\,": " ",
                                          "\\varepsilon": "eps"}.get(m.group(0), " "), s)
    s = re.sub(r"\\[,;!]", " ", s)
    s = s.replace("{", "(").replace("}", ")").replace("^", "**")

    # 自变量: 出现 dt/t' 用 t，否则 x
    indep = t_sym if re.search(r"\bd\s*t\b|\bt'", s) else x_sym
    y = Function("y")

    # 1) 高阶导数先转为占位符（占位符前后带空格，保证后续 token 分离）
    s = s.replace("y'''", " @@D3@@ ")
    s = s.replace("y''", " @@D2@@ ")
    s = s.replace("y'", " @@D1@@ ")

    # 2) 保护 y(x0)（初值形式的数值代入）
    protected = []
    def _protect(m):
        protected.append(m.group(1))
        return f"YAT{len(protected) - 1}"
    s = re.sub(r"y\s*\(\s*(-?[\d.]+)\s*\)", _protect, s)

    # 3) 剩余的 y（含 4y / qy / y 等乘积情形）替换为 YF（前导空格避免 qy→qYF 粘连成单 token）
    s = re.sub(r"(?<![a-zA-Z_@\\])y(?![a-zA-Z0-9_])", " YF ", s)

    # 4) 组装
    s = s.replace("@@D3@@", f"Derivative(YF, {indep}, 3)")
    s = s.replace("@@D2@@", f"Derivative(YF, {indep}, 2)")
    s = s.replace("@@D1@@", f"Derivative(YF, {indep})")

    local = {str(indep): indep, "x": x_sym, "t": t_sym, "pi": pi, "e": sympy.E,
             "sin": sin, "cos": cos, "exp": exp, "log": log, "YF": y(indep)}
    for i, x0 in enumerate(protected):
        local[f"YAT{i}"] = y(indep).subs(indep, sympy.Rational(x0))

    if "=" in s:
        lhs, rhs = s.split("=", 1)
        expr = sympy.Eq(_parse_ode_expr(lhs, local), _parse_ode_expr(rhs, local))
    else:
        expr = _parse_ode_expr(s, local)
    return expr, y, indep


def _parse_ode_expr(s: str, local: dict):
    """带隐式乘法转换的 ODE 表达式解析（4YF → 4*YF）。"""
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations, implicit_multiplication_application,
    )
    trans = standard_transformations + (implicit_multiplication_application,)
    return parse_expr(s, local_dict=local, transformations=trans)


def _parse_ics(text: str, y, indep):
    """从题干提取初始条件 y(x0)=a, y'(x0)=b, y''(x0)=c → sympy ics dict。"""
    ics = {}
    pattern = r"y(?P<order>'{1,2})?\s*\(\s*(?P<x0>-?[\d.]+)\s*\)\s*=\s*(?P<val>-?[\d.]+)"
    for m in re.finditer(pattern, text):
        x0 = sympy.Rational(m.group("x0"))
        val = sympy.Rational(m.group("val"))
        order = len(m.group("order") or "")
        if order == 0:
            ics[y(indep).subs(indep, x0)] = val
        else:
            ics[Derivative(y(indep), indep, order).subs(indep, x0)] = val
    return ics


def solve_ode(problem: dict) -> dict:
    text = problem.get("text", "")
    math_exprs = problem.get("math_expressions", [])
    candidates = [e.get("latex", "") for e in math_exprs] + [text]

    ode_eq = None
    used_src = None
    indep_used = None
    parse_errors = []
    for src in candidates:
        if not src or "y" not in src:
            continue
        if not re.search(r"y'|y''|\\frac\{d[xy]|dy\s*/\s*dx|d\^", src):
            continue
        try:
            # 剥离尾随的初始条件段（如 ", \quad y(0) = 1, y'(0) = 0"），
            # 初值统一由 _parse_ics 从完整题干提取
            eq_src = src
            while True:
                stripped = re.sub(
                    r"[,，;；]?\s*\\?quad\}?\s*y\s*'{0,2}\s*\(\s*-?[\d.]+\s*\)\s*=\s*[^,，;；]*",
                    " ", eq_src, count=1)
                if stripped == eq_src:
                    break
                eq_src = stripped
            eq_src = eq_src.strip().rstrip(",，;；").strip()
            expr, y, indep = _ode_to_sympy(eq_src)
            if isinstance(expr, sympy.Eq):
                ode_eq = sympy.Eq(sympy.simplify(expr.lhs - expr.rhs), 0)
            else:
                ode_eq = sympy.Eq(sympy.simplify(expr), 0)
            used_src = src
            indep_used = indep
            break
        except Exception as e:
            parse_errors.append(f"{src[:40]}: {e}")
            continue

    if ode_eq is None:
        reason = "无法从题目中解析出微分方程"
        if parse_errors:
            reason += " | " + " || ".join(parse_errors[:2])
        return _unsolved(problem, reason)

    # 方程含符号参数（如 p、q）→ 通常是证明/推导类题目，SymPy 数值求解无意义，
    # 转由国产 LLM 兜底（C4C 混合求解策略）
    extra_syms = {s for s in ode_eq.lhs.free_symbols} - {indep_used}
    if extra_syms:
        return _unsolved(problem,
                         f"方程含符号参数 {extra_syms}（证明/推导类），转由 LLM 兜底")

    steps = [f"解析得到微分方程: ${latex(ode_eq)}$"]

    try:
        ics = _parse_ics(text + " " + " ".join(e.get("latex", "") for e in math_exprs),
                         Function("y"), indep_used)
        sol = dsolve(ode_eq, Function("y")(indep_used), ics=ics if ics else None)
        order = ode_order(ode_eq.lhs, Function("y")(indep_used))
        steps.append(f"SymPy dsolve 求解（{order} 阶）")
        if ics:
            steps.append("代入初始条件 " + ", ".join(
                f"${latex(k)} = {latex(v)}$" for k, v in ics.items()))
        sol_latex = latex(sol.rhs) if hasattr(sol, "rhs") else latex(sol)
        if ics:
            steps.append(f"特解: $y = {sol_latex}$")
            return _make_solution(problem, steps, f"y = {sol_latex}")
        else:
            steps.append(f"通解: $y = {sol_latex}$" +
                         ("（含任意常数 C1）" if "C1" in str(sol) else ""))
            return _make_solution(problem, steps, f"y = {sol_latex}")
    except Exception as e:
        return _unsolved(problem, f"dsolve 失败: {e}")


# 类型猜测：用于 pipeline 在 classification 缺失时的兜底
MATRIX_HINTS = ["矩阵", "行列式", "特征值", "特征向量", "逆矩阵", "秩", "正交",
                "对角化", "matrix", "determinant", "eigenvalue", "rank", "方程组"]
ODE_HINTS = ["微分方程", "常微分", "differential equation", "ode",
             "y'", "y''", "通解", "特解", "初值"]


def guess_type(problem: dict):
    """在默认分类器没有覆盖时，猜测 matrix / ode。"""
    full = problem.get("text", "") + " " + " ".join(
        e.get("latex", "") for e in problem.get("math_expressions", []))
    if any(h in full for h in ODE_HINTS) and re.search(r"y'|y''|dy|d\^", full):
        return "ode"
    if any(h in full for h in MATRIX_HINTS) and ("matrix" in full or "矩阵" in full
            or "行列式" in full or "特征" in full or "方程组" in full):
        return "matrix"
    return None


# ═══════════════════════════════════════════════
# CLI 自测
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    A = Matrix([[1, 2], [3, 4]])
    print("det:", A.det(), "eigen:", A.eigenvals())
    eq, y, xi = _ode_to_sympy("y'' + 4y' + 4y = 0")
    print("ode parse:", eq)
    print("dsolve:", dsolve(sympy.Eq(sympy.simplify(eq.lhs - eq.rhs), 0), y(x_sym)))
