# C4C AI 使用日志（开发全过程记录）

> 作者：lishengdan ｜ 工具：WorkBuddy（AI 编程助手，模型驱动）+ DeepSeek API（流水线内推理引擎）
> 按时间线记录每一轮 AI 交互、prompt 策略、失败与修正。

## 阶段 0：任务理解与方案设计（AI 辅助）

- **Prompt 1**：把 CHALLENGE.md 全文交给 AI，要求「总结 starter kit 已有能力、必须做的两件事（迁移引擎/扩展学科）、必交清单」。AI 输出结构化摘要，确认 DeepSeek 属于挑战允许的国产模型。
- **决策交互**：AI 用选择题询问（a）是否有国产模型 API Key → 提供 DeepSeek Key；(b) 扩展学科 → 选线性代数+微分方程。
- **省成本约束**：用户要求尽可能节省 API。AI 提出「SymPy 优先 + LLM 兜底 + 批量合并 + 磁盘缓存」架构，后续全程遵守。

## 阶段 1：环境搭建（AI 执行）

- AI 检测本机 MiKTeX 损坏（只有 biber，无 xelatex），调用既有技能经验改用 **Tectonic 单文件方案**，下载到 `D:\tools\tectonic`（遵守「新工具装 D 盘」约束），缓存目录显式指到 `D:\tools\tectonic-cache`。
- Python 依赖装入 WorkBuddy 托管 venv（sympy/pdfplumber/python-docx/pypdf/requests/matplotlib/pymupdf），零全局污染。

## 阶段 2：代码开发（AI 编写，多轮迭代）

### 迭代 1：llm_engine.py（迁移核心件）
- AI 编写三供应商适配（DeepSeek/Qwen/Kimi）、.env 读取、磁盘缓存、多题合并单次调用。
- **Prompt 策略**：system prompt 要求「只输出 JSON 数组」，用户消息合并多题；用正则从回复中健壮提取 JSON（剥离 ```json 标记）。

### 迭代 2：solve_ext.py（线性代数+ODE 求解器）
- **失败 1**：`gram_schmidt` 从 `sympy.matrices` 导入报错（SymPy 1.14 路径变化）→ 改从 `sympy.matrices.gram_schmidt` 导入。
- **失败 2**：ODE 转换 `\by\b` 正则匹配不到 `4y`（词边界在 4 和 y 之间不存在）→ 改用环视断言。
- **失败 3**：`sympify(evaluate=False)` 对 Derivative 语法树报错 → 改用 `parse_expr + implicit_multiplication_application`（支持 `4YF` → `4*YF`）。
- **失败 4（隐蔽）**：`qy` 被 y→YF 替换成 `qYF` 单 token，解析失败 → 替换时插入空格 `" YF "`，依赖隐式乘法转换。
- **失败 5（最隐蔽）**：`solve_ode` 内部 `import sympy.ode` 导致 `sympy` 成为函数局部名，前置的 `sympy.Eq` 抛 `UnboundLocalError`。通过在 reason 中带出具体异常才定位 → 顶部统一导入（SymPy 1.14 顶层已导出 dsolve/ode_order）。
- **失败 6**：证明题 `y''+py'+qy=0` 含符号参数，SymPy 形式化求解出无意义答案 → 加守卫：检测到方程含 x 以外符号即转 LLM。
- 每次失败均由 AI「插桩打印真实异常 → 定位 → 修复 → 回归测试」闭环完成，共 6 轮。

### 迭代 3：ingest.py / render_latex.py / pipeline.py 改造
- PDF/Word 摄入实现；中文检测自动切 ctex 模板；Tectonic 编译集成（`TECTONIC_CACHE_DIR` 指向 D 盘）。
- **失败 7**：`\[\boxed{$|x|<\delta$, i.e. $-\delta<x<\delta$}\]` 嵌套定界符 → "Missing $"。修复：渲染器检测答案含 `$` 时按段落渲染。
- **失败 8**：ODE 步骤文本引用原始 LaTeX（`e^{-x}` 的 `^` 在文本模式）→ 同类编译错误。修复：步骤只保留 sympy.latex() 输出。

## 阶段 3：端到端验证（AI 执行 + 人工核对）

- 5 份作业全部跑通：Berkeley test1（8/8，0 API）、test2（9/10 SymPy + 1 LLM）、线性代数（7/8 + 1 LLM）、ODE（3/4 + 1 LLM）、英文混合（4/10 + 6 LLM）、PDF 真实作业链路（0/8 + 8 LLM）。
- **Prompt 亮点**：LLM 兜底采用「多题合并 + JSON 结构化输出 + temperature=0」，5 次 API 调用完成全部 40 题的兜底；缓存命中后重复运行 0 成本。
- AI 用 PyMuPDF 逐份扫描 PDF（页数/`??` 残留/未解析引用），并渲染 PNG 目检排版。
- 所有 LLM 答案逐题人工核对（行列式 −9、逆矩阵、特征值 5/2、对角化 P/D、Gram-Schmidt β₂=(1/2,−1/2,1)、ODE 特解代回验证等）——全部正确。

## AAR 复盘

### 做得好的
1. **成本控制架构**从第一天就设计进去，最终 5 次 API 调用完成整个挑战的全部验证，重复实验 0 成本。
2. LLM 答案**逐题人工核对**而不是相信模型输出——验证报告里每题都有独立验算过程。
3. 失败即固化：6 个 SymPy/正则坑全部转化为求解器里的守卫逻辑（如符号参数守卫）。

### 踩的坑
1. 最耗时的是 `import sympy.ode` 的 UnboundLocalError——异常被 `except: continue` 吞掉，浪费了一轮调试。**教训：兜底 except 必须把异常带进返回值**（后来成为 parse_errors 机制）。
2. PDF 摄入丢失 LaTeX 是架构级限制，最初期望 SymPy 也能处理 PDF 链路，实测后接受「PDF→LLM 为主」的现实并如实写进文档。
3. 正则处理 LaTeX 是脆弱路径（4 个坑都源于此），更稳妥的方向是 LLM 先把题目规范化成结构化 JSON 再交 SymPy——列入改进项。

### 改进方案（如继续迭代）
1. LLM 预规范化：摄入后先让 LLM 把全部题目统一转成规范 LaTeX/结构化 JSON（一次调用），SymPy 成功率会从「分类依赖正则」提升一档；
2. 接入 Tesseract/Qwen-VL OCR 支持扫描件；
3. matplotlib 图形题自动作图；
4. 把 DeepSeek 换 Qwen 做横向对比（代码已就绪，只差 API Key）。
