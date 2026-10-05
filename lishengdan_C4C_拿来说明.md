# C4C 拿来说明 —— 从 starter kit 拿了什么、改了什么

> 作者：lishengdan

## 1. 拿了什么（拿来主义基座）

| 拿来的资产 | 来源 | 用途 |
|-----------|------|------|
| 五阶段流水线骨架（ingest→parse→solve→render→pipeline） | starter kit `scripts/` | 整体架构原样保留，只做扩展不做重写 |
| T-box 分类器 + 关键词分类 | `classify.py` / `parse_problems.py` | 题目路由机制原样复用 |
| 微积分极限全部求解器（ε-δ/切线/极限/概念模板） | `solve.py` 约 1500 行 | 基线能力原样保留，一行未改核心逻辑 |
| LaTeX 表达式解析器 `safe_parse` | `solve.py` | 线性方程组求解复用它解析方程 |
| 作业 LaTeX 模板 | `render_latex.py` / `references/homework_template.tex` | 前导结构、problem/solution 环境、boxed 答案样式 |
| Berkeley 测试集 + Claude 验证报告 | `test_cases/` | 作为基线对比的黄金标准 |
| 外部库 | SymPy（符号计算）、pdfplumber、python-docx、PyMuPDF | 挑战文档推荐方案 |

## 2. 改了什么（迁移与扩展）

### 2.1 新增文件（迁移核心）

| 文件 | 内容 | 为什么必须新写 |
|------|------|---------------|
| `scripts/llm_engine.py` | DeepSeek/Qwen/Kimi 三供应商适配、.env 密钥管理、多题合并单次调用、磁盘缓存 | Claude 版没有独立 LLM API 层（推理由 Claude Code agent 自己做）；迁移到国产模型必须显式建这一层 |
| `scripts/solve_ext.py` | 线性代数求解器（8 种题型）+ ODE 求解器 + 类型兜底猜测 | starter kit 中是空壳"学生扩展点" |

### 2.2 修改的文件

| 文件 | 改动 | 改动性质 |
|------|------|---------|
| `scripts/solve.py` | `solve_matrix`/`solve_ode` 空壳 → 委托 solve_ext；`solve_problem` 加新学科兜底分类 | 接线，核心未动 |
| `scripts/ingest.py` | `read_pdf_text`/`read_docx` 从 NotImplementedError → 完整实现 | 补全学生扩展点 |
| `scripts/render_latex.py` | ① 中文检测自动切 ctex 模板 ② compile_pdf 优先 Tectonic ③ 混合文本答案渲染修复 | 扩展 |
| `scripts/pipeline.py` | 插入 Stage 3b（LLM 兜底），SymPy 未解题合并交给 DeepSeek 后回写 | 扩展 |

## 3. Claude 版本与国产模型版本的关键差异

| 维度 | Claude 版（starter kit） | 国产模型版（本作品） |
|------|--------------------------|---------------------|
| 推理引擎 | Claude Code agent 隐式推理，无 API 成本核算 | DeepSeek `deepseek-chat` 显式 API 层，可切换 Qwen/Kimi |
| 推理触发 | agent 自行决定何时"思考" | 明确规则：**仅 SymPy 未解出的题**才调 LLM |
| 成本 | Claude 订阅内不可见 | 5 次调用完成 40 题验证，缓存后 0 成本（省钱三件套：SymPy 优先/批量合并/磁盘缓存） |
| 学科覆盖 | 微积分极限（94.4%） | + 线性代数、微分方程、混合领域 |
| 输入格式 | 仅 Markdown | + PDF、Word |
| 编译依赖 | 需本机 pdflatex/xelatex | Tectonic 单文件（XeTeX 内核），免安装发行版 |
| 中文支持 | 手动 XeLaTeX 流程 | 自动检测中文 → ctex 模板 |

## 4. 没拿什么（有意的取舍）

- **没拿** starter kit 的 `bootstrap.py` 自动装依赖逻辑（venv 已预装，避免运行时联网装包的不可控）；
- **没拿** `oracles/` 教学语料的检索增强（retrieve.py 保留但核心求解走 SymPy+LLM 双引擎，检索增强列为改进项）；
- **没重写** 任何微积分极限求解器——基线已验证 94.4%，重写只会引入回归风险。
