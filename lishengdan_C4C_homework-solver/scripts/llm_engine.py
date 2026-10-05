#!/usr/bin/env python3
"""
国产大模型求解引擎（C4C 迁移核心件）
====================================

这是从 Claude Code 迁移到国产大模型的关键模块：
  - Claude 版本中，推理由 Claude Code agent 自身完成（无独立 API 层）
  - 迁移版本将推理抽象为独立引擎，支持任意 OpenAI 兼容协议的国产模型：
      * DeepSeek  (https://api.deepseek.com)                ← 默认
      * Qwen      (dashscope compatible-mode)               ← 换环境变量即可
      * Kimi      (https://api.moonshot.cn/v1)              ← 换环境变量即可

省 API 成本设计（省钱三件套）：
  1. SymPy 优先：本引擎只处理 SymPy 求解失败后的"兜底"题目
  2. 批量合并：多道未解题目合并为【一次】API 调用
  3. 磁盘缓存：相同题目文本 + 模型 → 直接读缓存，重复运行零成本

用法（一般由 pipeline.py 自动调用，也可手动）:
    python llm_engine.py parsed.json solutions.json output.json
"""

import json
import hashlib
import os
import re
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = SKILL_ROOT / ".llm_cache.json"

# ─────────────────────────────────────────────
# .env 加载（避免把 Key 写进代码/提交包）
# ─────────────────────────────────────────────

def load_env_file():
    """从可能的 .env 位置读取 KEY=VALUE（不覆盖已有环境变量）。"""
    candidates = [
        SKILL_ROOT / ".env",
        SKILL_ROOT.parent / ".env",
        Path("D:/c4c_work/.env"),   # 本机开发约定位置
    ]
    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env_file()

# ─────────────────────────────────────────────
# 供应商配置（OpenAI 兼容协议，只换 base_url/key/model）
# ─────────────────────────────────────────────

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "name": "DeepSeek (深度求索)",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_env": "DASHSCOPE_API_KEY",
        "model_env": "QWEN_MODEL",
        "default_model": "qwen-plus",
        "name": "Qwen (通义千问)",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "key_env": "MOONSHOT_API_KEY",
        "model_env": "KIMI_MODEL",
        "default_model": "moonshot-v1-8k",
        "name": "Kimi (月之暗面)",
    },
}


def get_provider():
    """根据 LLM_PROVIDER 环境变量返回可用供应商配置；不可用返回 None。"""
    provider_id = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    cfg = PROVIDERS.get(provider_id)
    if not cfg:
        return None
    api_key = os.environ.get(cfg["key_env"], "").strip()
    if not api_key:
        return None
    model = os.environ.get(cfg["model_env"], cfg["default_model"])
    return {"id": provider_id, "api_key": api_key, "model": model,
            "base_url": cfg["base_url"], "name": cfg["name"]}


def is_available() -> bool:
    return get_provider() is not None

# ─────────────────────────────────────────────
# 底层 chat 调用
# ─────────────────────────────────────────────

def chat(messages: list, max_tokens: int = 3000, temperature: float = 0.0,
         timeout: int = 120) -> str:
    """调用 OpenAI 兼容 chat/completions 接口。"""
    import requests  # 延迟导入
    cfg = get_provider()
    if not cfg:
        raise RuntimeError("未配置国产模型 API Key（设置 DEEPSEEK_API_KEY 等环境变量）")
    resp = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {cfg['api_key']}",
                 "Content-Type": "application/json"},
        json={
            "model": cfg["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ─────────────────────────────────────────────
# 缓存
# ─────────────────────────────────────────────

def _cache_key(problem: dict, model: str) -> str:
    basis = json.dumps({
        "model": model,
        "id": problem.get("id"),
        "text": problem.get("text"),
        "math": [e.get("latex") for e in problem.get("math_expressions", [])],
        "subs": [s.get("text") for s in problem.get("sub_problems", [])],
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

# ─────────────────────────────────────────────
# 批量求解：多题合并为一次调用
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """你是大学数学解题专家。你会收到若干道用 SymPy 符号计算无法直接求解的\
数学题（证明题、概念题、需要推理的文字题）。请逐题给出严谨解答。

要求：
1. 只输出一个 JSON 数组，不要输出任何其他文字（不要 markdown 代码块标记）。
2. 数组每个元素格式：
   {"problem_id": "<题目id>", "solved": true/false,
    "steps": ["解答步骤，行内的数学用 $...$ LaTeX 包裹", ...],
    "answer": "最终答案的纯文本",
    "answer_latex": "最终答案的 LaTeX（不含 \\boxed）"}
3. steps 每步一个字符串，简洁但完整；证明题要给出关键推理链条。
4. 若确实无法求解，设 solved=false 并在 steps 里说明原因。
5. 全部使用简体中文。"""


def _render_problem_for_llm(problem: dict) -> str:
    parts = [f"【题目 {problem.get('id')}】", problem.get("text", "")]
    for e in problem.get("math_expressions", []):
        if e.get("latex"):
            parts.append(f"公式: {e['latex']}")
    for sub in problem.get("sub_problems", []):
        parts.append(f"  子题: {sub.get('text', '')}")
        for e in sub.get("math_expressions", []):
            if e.get("latex"):
                parts.append(f"  子题公式: {e['latex']}")
    return "\n".join(parts)


def _extract_json_array(text: str):
    """从模型回复中健壮地提取 JSON 数组。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("回复中未找到 JSON 数组")
    return json.loads(text[start:end + 1])


def batch_solve(problems: list, verbose: bool = True) -> list:
    """
    批量求解题目列表（SymPy 失败的兜底）。
    返回 solution dict 列表（与 solve.py 输出格式一致）。
    相同题目命中缓存则不消耗 API。
    """
    cfg = get_provider()
    if not cfg or not problems:
        return []

    cache = _load_cache()
    results, need_llm = [], []
    for p in problems:
        key = _cache_key(p, cfg["model"])
        if key in cache:
            sol = cache[key]
            sol["solver"] = f"llm:{cfg['id']}(cached)"
            results.append(sol)
        else:
            need_llm.append((p, key))

    if not need_llm:
        if verbose:
            print(f"   [LLM] {len(results)} 道题全部命中缓存，0 次 API 调用")
        return results

    if verbose:
        print(f"   [LLM] 引擎: {cfg['name']} / {cfg['model']}")
        print(f"   [LLM] 缓存命中 {len(results)} 道，本次 API 调用 1 次（合并 {len(need_llm)} 道题）")

    prompt_body = "\n\n".join(_render_problem_for_llm(p) for p, _ in need_llm)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请解答以下 {len(need_llm)} 道题：\n\n{prompt_body}"},
    ]

    last_err = None
    for attempt in range(2):  # 最多重试 1 次
        try:
            reply = chat(messages, max_tokens=3000, temperature=0.0)
            items = _extract_json_array(reply)
            by_id = {}
            for item in items:
                pid = str(item.get("problem_id", ""))
                by_id[pid] = item
            for p, key in need_llm:
                item = by_id.get(str(p.get("id")), {})
                sol = {
                    "problem_id": p.get("id"),
                    "problem_text": p.get("text"),
                    "solved": bool(item.get("solved", False)),
                    "steps": item.get("steps", []),
                    "answer": item.get("answer"),
                    "answer_latex": item.get("answer_latex", ""),
                    "solver": f"llm:{cfg['id']}",
                    "sub_solutions": [],
                    "reason": "" if item.get("solved") else "LLM 未能求解",
                }
                cache[key] = {k: v for k, v in sol.items() if k != "solver"}
                results.append(sol)
            _save_cache(cache)
            return results
        except Exception as e:
            last_err = e
            time.sleep(2)

    if verbose:
        print(f"   [LLM] 调用失败: {last_err}")
    # 失败也要返回结构（未解状态）
    for p, _ in need_llm:
        results.append({
            "problem_id": p.get("id"), "problem_text": p.get("text"),
            "solved": False, "steps": [], "answer": None, "answer_latex": "",
            "solver": f"llm:{cfg['id']}", "sub_solutions": [],
            "reason": f"LLM 调用失败: {last_err}",
        })
    return results

# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 4:
        print("用法: python llm_engine.py parsed.json solutions.json output.json")
        sys.exit(1)
    parsed = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    solutions = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    unsolved = [p for p, s in zip(parsed, solutions) if not s.get("solved")]
    print(f"[LLM 引擎] 待兜底求解: {len(unsolved)} 道")
    llm_sols = batch_solve(unsolved)
    llm_by_id = {str(s["problem_id"]): s for s in llm_sols}
    for s in solutions:
        merged = llm_by_id.get(str(s["problem_id"]))
        if merged and merged.get("solved"):
            s.update(merged)
    Path(sys.argv[3]).write_text(
        json.dumps(solutions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  完成 → {sys.argv[3]}")


if __name__ == "__main__":
    main()
