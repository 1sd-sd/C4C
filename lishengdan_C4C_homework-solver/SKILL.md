# Homework Auto-Solver & Formatter

> 从作业文件到可提交 PDF，一条命令搞定。
> Ontology-grounded, retrieval-augmented homework solving.

## Skill Invocation

**Triggers:** "solve this homework", "auto-solve worksheet", "run the homework solver", "求解作业", "自动解题", or when a user provides a math worksheet (.md, .pdf, .docx, .png) and asks for solutions.

**Usage:** When triggered, the agent should:

1. **Locate the input file.** The user may upload a file, paste text, or point to a path. If text is pasted, save it as a temporary `.md` file first.

2. **Run the pipeline:**
```bash
SKILL_DIR="<path-to-this-skill-directory>"
python "$SKILL_DIR/scripts/pipeline.py" <input_file> <output_dir> [--compile] [--course "Math 1A"] [--student "Name"]
```

3. **Report results.** Show the solve rate (X/Y solved), list any unsolved problems, and provide the output files (`.tex` and optionally `.pdf`).

4. **For Chinese output:** Generate Chinese worksheets and answer sheets using XeLaTeX with Noto Sans CJK SC. See the exemplar `*_cn.pdf` files at the project root.

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input` | (required) | Path to homework file (.md, .pdf, .docx, image) |
| `output_dir` | (required) | Where to write output files |
| `--compile` | off | Compile LaTeX to PDF (requires pdflatex/xelatex) |
| `--course` | "Mathematics" | Course name for header |
| `--student` | "Student" | Student name for header |
| `--title` | "Homework Solutions" | Title for the document |

**Output files:**
| File | Content |
|------|---------|
| `1_ingested.json` | Raw text extraction with section boundaries |
| `2_parsed.json` | Structured problems with classifications |
| `3_solutions.json` | Solutions with steps, answers, and solve status |
| `homework.tex` | Formatted LaTeX document |
| `homework.pdf` | Compiled PDF (if `--compile` used) |

**Dependencies:** `pip install sympy pyyaml` (see `requirements.txt`)

**Example agent interaction:**
```
User: "Here's my Math 1A worksheet on limits. Can you solve it?"
Agent: [saves uploaded file] → [runs pipeline] → "Solved 9/10 problems (90%).
       AP3 (geometric derivation) requires manual solving.
       Here's your answer sheet: [link to homework.tex]"
```

---

## Architecture Overview

This skill uses an **ontology-grounded** approach: domain knowledge (concepts, solution methods, classification rules) is separated from problem instances. The solver's capability is determined by what it has *learned* from oracle sources, not by hard-coded patterns.

**The key insight:** Solve rate = domain coverage. To solve more problems, expand the domain knowledge — don't write more regex.

The pipeline works in 5 stages:
```
Input → Ingest → Parse + Classify → Solve → Render LaTeX → Compile PDF
```

Study the code in `scripts/` and the domain definitions in `domain_skills/` to understand how classification, retrieval, and solving work together. The `oracles/` directory contains the source knowledge that was distilled into the domain definitions.

**Oracle sources** (knowledge distilled from these into the solver):
1. **Textbook** — Stewart, Calculus: Early Transcendentals, Ch. 2
2. **Exemplars** — Berkeley Math 1A Worksheets 3–4
3. **Study Guide** — common errors, misconceptions, learning sequence
4. **Instructor + Pedagogy Guides** — proof methods, scaffolding, grading rubrics

---

## Quick Start

### Dependencies

```bash
pip install sympy pyyaml --break-system-packages
# Optional (extended format support):
# pip install pdfplumber python-docx pytesseract Pillow
```

### One-Command Run

```bash
python scripts/pipeline.py examples/sample_homework.md output/
```

### Step-by-Step

```bash
# Stage 1: Document Ingestion
python scripts/ingest.py homework.md output/1_ingested.json

# Stage 2: Problem Parsing + Classification
python scripts/parse_problems.py output/1_ingested.json output/2_parsed.json

# Stage 3: Solving
python scripts/solve.py output/2_parsed.json output/3_solutions.json

# Stage 4: LaTeX Generation
python scripts/render_latex.py output/3_solutions.json output/homework.tex

# Stage 5: PDF Compilation (requires LaTeX)
python scripts/render_latex.py output/3_solutions.json output/homework.tex --compile
```

## Five-Stage Pipeline

### Stage 1 — Document Ingestion (`ingest.py`)

Reads homework files and extracts structured text with section boundaries.

| Format | Status | Implementation |
|--------|--------|----------------|
| Markdown (.md) | ✅ Starter | Direct parse |
| PDF (text) | 🔧 Student L2 | pdfplumber |
| PDF (scanned) | 🔧 Student L2 | Tesseract OCR |
| Word (.docx) | 🔧 Student L2 | python-docx |
| Image (.png/.jpg) | 🔧 Student L3 | Claude Vision |

### Stage 2 — Problem Parsing (`parse_problems.py`)

Extracts problem structure: ID, text, math expressions, sub-problems.
Classifies each problem against the domain knowledge.

Recognized problem ID formats:
```
Problem 1 / 题 1 / 1. / 1) / Q1 / Exercise 1
Sub-problems: (a), a), a.
Section detection: Questions, Problems, Additional Problems, Part A/B/C
Heading-embedded IDs: ### Problem 1: Title
```

### Stage 3 — Solving (`solve.py`)

The solver routes each problem through:

1. **Classify** — match problem features to domain knowledge
2. **Retrieve** — find the appropriate solution method
3. **Instantiate** — bind problem variables to the method
4. **Execute** — run using the prescribed tool (SymPy, template, etc.)
5. **Validate** — check answer form

#### Current Domain Coverage (Limits)

The starter kit covers **calculus limits** — tangent lines, ε-δ proofs, one-sided limits, squeeze theorem, continuity, and more. See `domain_skills/calculus_limits.yaml` for the full definition.

#### Adding a New Domain

To cover a new problem domain (e.g., derivatives, integrals, linear algebra):

1. Create `domain_skills/your_domain.yaml` — define concepts, solution methods, classification rules
2. Implement solver templates in `solver_templates/`
3. Register in the pipeline — the classify → retrieve → solve chain handles routing automatically

Study the existing `calculus_limits.yaml` carefully as a reference for your own domains.

### Stage 4 — LaTeX Generation (`render_latex.py`)

Generates professional LaTeX with:
- Course header with student name
- Problem/solution structure with `\problem{}` and `\solution{}` environments
- Boxed final answers
- Proper amsmath formatting

### Stage 5 — PDF Compilation

Requires LaTeX environment (pdflatex or xelatex), or upload `.tex` to Overleaf.

## Extending the Solver

### The Right Way: Expand Domain Knowledge

```yaml
# Add a new concept node to domain_skills/your_domain.yaml
- id: integration_by_parts
  type: solution_method
  concept: integral
  name: "Integration by parts"
  applies_when: "Product of two functions where one simplifies under differentiation"
  tool: sympy
  solver_template: sympy_solvers/integration_by_parts.py
  input_schema:
    u_expr: "function to differentiate"
    dv_expr: "function to integrate"
  output_form: "expression + C"
```

Then implement the solver template:
```python
# solver_templates/sympy_solvers/integration_by_parts.py
def solve(u_expr, dv_expr, variable):
    u = u_expr
    v = integrate(dv_expr, variable)
    result = u * v - integrate(v * diff(u, variable), variable)
    return {"solved": True, "answer": result, ...}
```

### The Quick Way: Add a Solver Function (backward compatible)

```python
# In solve.py — register directly
def solve_my_topic(problem: dict) -> dict:
    return _make_solution(problem, steps, answer)

SOLVERS["my_topic"] = solve_my_topic
```

## File Structure

```
c4c-homework-solver-starter/
├── SKILL.md                          ← This file
├── CHALLENGE.md                      ← Student challenge guide (L1→L4)
├── scripts/
│   ├── ingest.py                     ← Stage 1: Document ingestion
│   ├── parse_problems.py             ← Stage 2: Problem parsing + classification
│   ├── classify.py                   ← Classifier (concept → solver mapping)
│   ├── retrieve.py                   ← Retriever (solver template lookup)
│   ├── solve.py                      ← Stage 3: Solving + conceptual templates
│   ├── render_latex.py               ← Stage 4: LaTeX generation + Stage 5: PDF
│   └── pipeline.py                   ← One-command orchestrator
├── domain_skills/                    ← Domain knowledge definitions
│   └── calculus_limits.yaml          ← Limits domain (Berkeley Math 1A)
├── solver_templates/                 ← Parameterized solver code
│   ├── sympy_solvers/
│   │   ├── limit_direct.py           ← Direct limit computation
│   │   └── limit_dne.py              ← Limit DNE proof
│   └── template_solvers/
│       └── epsilon_delta_notation.py ← ε-δ notation templates
├── oracles/                          ← Oracle source documents
│   ├── 01_textbook_stewart.md
│   ├── 02_study_guide.md
│   ├── 03_instructor_guide.md
│   ├── 04_pedagogy_guide.md
│   └── 05_exemplars.md
├── references/
│   ├── homework_template.tex         ← LaTeX template
│   └── sympy_cheatsheet.md          ← SymPy quick reference
├── examples/
│   └── sample_homework.md           ← 10-problem sample input
├── test_cases/
│   ├── test1_tangent_epsilon_delta.md  ← Berkeley Worksheet 3 (8 problems)
│   ├── test2_limits.md                 ← Berkeley Worksheet 4 (10 problems)
│   ├── test1_output/                   ← Validated output for test 1
│   └── test2_output/                   ← Validated output for test 2
├── test1_worksheet_cn.pdf            ← Chinese worksheet (切线与 ε-δ)
├── test1_answers_cn.pdf              ← Chinese answers with solution steps
├── test2_worksheet_cn.pdf            ← Chinese worksheet (函数的极限)
├── test2_answers_cn.pdf              ← Chinese answers with solution steps
├── challenge_answers_cn.tex          ← Advanced challenge problems LaTeX source
└── challenge_answers_cn.pdf          ← Advanced challenge answers (5 problems)
```

## Test Results

Validated against Berkeley Math 1A Worksheets 3–4:

| Test Case | Problems | Solved | Rate | Notes |
|-----------|----------|--------|------|-------|
| Test 1: Tangent & ε-δ | 8 | 8 | **100%** | All subs solved |
| Test 2: Limits | 10 | 9 | **90%** | Only AP3 (geometric derivation) unsolved |
| **Combined** | **18** | **17** | **94.4%** | Limits domain only |
| Challenge (advanced) | 5 | 2 | **40%** | Beyond limits domain (manual: 5/5) |

**Important caveat:** The 94.4% rate applies to the **limits domain only**. When tested against 5 advanced problems (integration, optimization, combinatorics, physics), the pipeline auto-solved only 2/5 (40%). This demonstrates that the solver's capability is scoped to its domain knowledge — extending to new domains is your challenge (see CHALLENGE.md).

## Chinese PDF Outputs

| File | Content | Pages |
|------|---------|-------|
| `test1_worksheet_cn.pdf` | 工作单 3：切线与 ε-δ 预备知识 | 2 |
| `test1_answers_cn.pdf` | 参考答案（含解题步骤） | 3 |
| `test2_worksheet_cn.pdf` | 工作单 4：函数的极限 | 2 |
| `test2_answers_cn.pdf` | 参考答案（含解题步骤） | 5 |
| `challenge_answers_cn.pdf` | 高等微积分挑战题参考答案 | 7 |

Chinese PDFs use XeLaTeX + Noto Sans CJK SC with `\XeTeXlinebreaklocale "zh"` for proper CJK line-breaking.

## Limitations & What You Can Build

| Current Limitation | What's Missing | Your Extension Path |
|-------------------|---------------|---------------------|
| Only solves limits problems | No integration/derivatives/linear algebra domains | Build new domain YAML + solvers (L2) |
| Proof problems fail | No LLM solver for multi-step reasoning | Add `tool: llm` solver template (L4) |
| No PDF/image input | Only Markdown ingestion implemented | Add pdfplumber, OCR, Claude Vision (L2) |
| No learning loop | Solver doesn't improve from experience | Add success tracking + oracle invocation (L4) |
| Geometric reasoning | No spatial/construction reasoning | Add geometric concept + LLM solver (L4) |

**What's already working:**
- Counterexample reasoning via knowledge templates
- Abstract-function sub-problems via template-first matching
- Graph sketching subs via placeholder recognition
- Chinese PDF generation with professional formatting
- Heading-format problem ID parsing
