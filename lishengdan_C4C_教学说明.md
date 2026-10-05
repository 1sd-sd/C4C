# C4C 教学说明 —— 安装与使用

> 5 分钟上手：从作业文件到可提交 PDF。

## 1. 环境要求

| 组件 | 要求 | 说明 |
|------|------|------|
| Python | ≥ 3.10 | 开发验证用 3.13 |
| 依赖 | sympy, pdfplumber, python-docx, pypdf, requests | `pip install -r requirements.txt` |
| LaTeX | **不需要安装** | 内置 Tectonic 支持；也可用本机 pdflatex/xelatex 或 Overleaf |
| 国产模型 Key（可选） | DeepSeek / Qwen / Kimi 任一 | 不配置则纯 SymPy 模式（微积分极限/线代/ODE 数值题仍可解） |

## 2. 安装

```bash
cd lishengdan_C4C_homework-solver
pip install -r requirements.txt

# 启用 LLM 兜底（可选，三选一）：
# 方式 A：环境变量
set DEEPSEEK_API_KEY=sk-xxxx        # Windows
export DEEPSEEK_API_KEY=sk-xxxx     # Linux/Mac
# 方式 B：在技能目录旁建 .env 文件写入 DEEPSEEK_API_KEY=sk-xxxx

# 可选切换供应商（默认 deepseek）：
set LLM_PROVIDER=qwen               # qwen | kimi | deepseek
set DASHSCOPE_API_KEY=sk-xxxx       # 对应供应商的 Key
```

## 3. 一条命令跑通

```bash
# Markdown 作业
python scripts/pipeline.py examples/linalg_homework_zh.md output/ --compile ^
       --course "线性代数（A）" --student "你的名字" --title "第 3 次作业"

# PDF 作业（文本型）
python scripts/pipeline.py homework.pdf output/ --compile

# Word 作业
python scripts/pipeline.py homework.docx output/ --compile
```

输出目录内：
| 文件 | 内容 |
|------|------|
| `1_ingested.json` | Stage 1 摄入的结构化文本 |
| `2_parsed.json` | Stage 2 题目解析（题号/公式/类型） |
| `3_solutions.json` | Stage 3 求解结果（步骤/答案/求解器来源） |
| `homework.tex` | Stage 4 LaTeX 排版 |
| `homework.pdf` | Stage 5 编译产物（`--compile` 时） |

## 4. 支持的课程/题型

| 学科 | 题型 | 求解引擎 |
|------|------|---------|
| 微积分（极限） | 切线、ε-δ、单侧/双侧极限、概念题 | SymPy + 模板（基线 94.4%→100%） |
| 线性代数 | 行列式、逆矩阵、秩、特征值/向量、对角化、Gram-Schmidt、线性方程组、矩阵乘法 | SymPy |
| 微分方程 | 一阶线性/可分离、二阶常系数（齐次/初值问题） | SymPy dsolve |
| 证明题/概念题/复杂推理 | 任意学科 | DeepSeek（LLM 兜底） |
| 大学物理等 | 公式计算类可尝试，未系统验证 | SymPy/LLM |

## 5. 常见问题

**Q：会花多少 API 钱？**
A：只有 SymPy 解不出的题才调 LLM，且多题合并成 1 次调用。实测 40 题全流程 5 次调用；缓存后重复运行 0 次。

**Q：换一门课怎么复用？**
A：直接换输入文件。解析器识别 `Problem N / 题 N / N. / QN` 格式；新题型若 SymPy 解不出会自动走 LLM 兜底。

**Q：PDF 是扫描件能处理吗？**
A：当前仅支持文本型 PDF（pdfplumber）。扫描件需 OCR，未实现。

**Q：如何换模型？**
A：`llm_engine.py` 的 PROVIDERS 字典已内置 deepseek/qwen/kimi 三家（OpenAI 兼容协议），设环境变量即可切换，无需改代码。

**Q：编译报错怎么办？**
A：优先确认 Tectonic 可用（`D:/tools/tectonic/tectonic.exe` 或 PATH 中有 tectonic）；也可把 `homework.tex` 上传 Overleaf 在线编译。
