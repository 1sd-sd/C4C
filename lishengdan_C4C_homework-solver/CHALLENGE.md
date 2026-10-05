# C4C Challenge: Homework Auto-Solver

> 从一套作业到可提交答案，让 AI 自动求解。
> Build an AI agent that solves homework from raw worksheets to submission-ready PDFs.

## Challenge Overview

You have a working exemplar that achieves **94.4% solve rate** on Berkeley Math 1A Worksheets 3–4 (limits domain). Your challenge is to **extend it to new domains** and **improve the architecture**.

Study the working code carefully — understand *how* it achieves that solve rate, then apply the same principles to new domains.

### Caveat: Domain-Scoped Performance

The 94.4% rate applies **only to the limits domain**. When tested against 5 advanced calculus problems (integration, optimization, combinatorics, physics), the pipeline auto-solved only **2/5 (40%)**. This is by design — the solver's knowledge boundary is real, and extending it is your challenge.

See `challenge_answers_cn.pdf` for all 5 problems with full manual solutions — these serve as target exemplars for your domain extensions.

## How to Use This Starter Kit

### 1. Setup
```bash
pip install -r requirements.txt
```

### 2. Run the Exemplar
```bash
# Full pipeline on test case 1 (tangent lines + ε-δ)
python scripts/pipeline.py test_cases/test1_tangent_epsilon_delta.md output/test1/

# Full pipeline on test case 2 (limits)
python scripts/pipeline.py test_cases/test2_limits.md output/test2/

# Step-by-step (to see each stage)
python scripts/ingest.py test_cases/test1_tangent_epsilon_delta.md output/1_ingested.json
python scripts/parse_problems.py output/1_ingested.json output/2_parsed.json
python scripts/solve.py output/2_parsed.json output/3_solutions.json
python scripts/render_latex.py output/3_solutions.json output/homework.tex
```

### 3. Study the Code
Read these files in order:
1. `SKILL.md` — executive summary, pipeline usage
2. `domain_skills/calculus_limits.yaml` — the domain knowledge definition (study this carefully!)
3. `scripts/solve.py` — how the solver works (classification, retrieval, execution)
4. `scripts/parse_problems.py` — how problems are parsed and classified
5. `oracles/` — the knowledge sources that were distilled into the domain definition

### 4. Discover the Key Insight
The solver's power comes from its domain knowledge, not from code complexity. **Figure out the architecture by reading the code**, then apply the same design principles to new domains. The biggest question you need to answer:

> What makes a problem solvable by this pipeline, and what makes it unsolvable?

---

## Challenge Levels

### Level 1: Run & Understand (目标: 理解架构)

**Goal:** Reproduce the exemplar results and reverse-engineer the architecture.

**Tasks:**
- [ ] Run the full pipeline on both test cases. Verify you get 8/8 and 9/10.
- [ ] Read `domain_skills/calculus_limits.yaml` and answer:
  - How is domain knowledge organized? What are the key structures?
  - How does the solver decide which method to use for a problem?
  - What role do the oracle sources play?
- [ ] Trace ONE problem through the pipeline manually:
  - Pick any problem from test case 2
  - Follow it through each stage (ingest → parse → classify → solve → render)
  - Document what happens at each stage and why
- [ ] Write a 1-page summary of the architecture in your own words.
  - What is the design principle that makes this work?
  - How would you explain it to someone who hasn't seen the code?

**Deliverable:** Written trace + architecture summary (Markdown or PDF)

---

### Level 2: Extend to a New Domain (目标: 60%+ on a NEW worksheet)

**Goal:** Add a new domain and achieve ≥60% solve rate on a worksheet you haven't seen before.

**Choose ONE of:**

#### Option A: Derivatives Domain
Create a domain definition covering:
- [ ] Power rule, product rule, quotient rule, chain rule
- [ ] Derivative as limit definition: f'(a) = lim_{h→0} [f(a+h) - f(a)] / h
- [ ] Higher-order derivatives
- [ ] Implicit differentiation
- [ ] Related rates (basic)

#### Option B: Integration Domain
Create a domain definition covering:
- [ ] Antiderivatives and indefinite integrals
- [ ] Basic integration rules (power, trig, exponential)
- [ ] Definite integrals and the Fundamental Theorem of Calculus
- [ ] U-substitution
- [ ] Integration by parts (basic)

#### Option C: Linear Algebra Domain
Create a domain definition covering:
- [ ] Matrix operations (add, multiply, transpose)
- [ ] Determinants (2×2, 3×3)
- [ ] Systems of linear equations (Gaussian elimination)
- [ ] Eigenvalues and eigenvectors (2×2)
- [ ] Vector operations (dot product, cross product)

#### Option D: Advanced Calculus Challenge Problems
Use the 5 problems in `challenge_answers_cn.pdf` as your test set:
- [ ] Wine Barrel Volume → needs integration domain (disk method, algebraic substitution)
- [ ] EPQ Production Cost → needs optimization domain (piecewise integration, cost minimization)
- [ ] Fermat's Principle / Snell's Law → needs optimization + physics concepts
- [ ] Telescoping Cosine Sums → needs series domain (product-to-sum, telescoping proofs)
- [ ] Binomial Theorem Proof → needs proof-by-differentiation concept

Manual solutions with full derivations are provided in the challenge PDF for reference.

**For any option, you must:**
- [ ] Gather at least 2 oracle sources (textbook + exemplars)
- [ ] Define a domain knowledge structure following the pattern in `calculus_limits.yaml`
- [ ] Write classification rules that route problems to the right solvers
- [ ] Implement solver templates (SymPy or template-based)
- [ ] Handle non-computational questions (definitions, theorems, counterexamples)
- [ ] Test on a real worksheet (provide the worksheet + results)
- [ ] Achieve ≥60% solve rate on that worksheet

**Deliverable:** Domain definition + solver templates + test results + brief writeup

---

### Level 3: Knowledge-Enriched Domain (目标: 75%+ with knowledge distillation)

**Goal:** Systematically improve your L2 domain by ingesting additional knowledge sources.

**Tasks:**
- [ ] Find and ingest ≥2 additional knowledge sources beyond textbook + exemplars:
  - Study guide, instructor guide, pedagogy guide, worked example set, or video transcript
- [ ] For each source, document what was extracted:
  - New concepts? New classification rules? New templates? Common errors?
- [ ] Add the distilled knowledge to your domain definition
- [ ] Add ≥5 new templates for non-computational questions
- [ ] Add ≥3 new classification rules based on the new knowledge
- [ ] Demonstrate measurable improvement: show before/after solve rates
- [ ] Achieve ≥75% solve rate on your test worksheet

**Bonus tasks:**
- [ ] Add Chinese language support to your output (XeLaTeX + CJK fonts)
- [ ] Generate both worksheet and answer sheet PDFs (follow the exemplar Chinese PDFs)

**Deliverable:** Updated domain definition + knowledge source documents + before/after comparison + writeup

---

### Level 4: Architecture Innovation (目标: 90%+ or novel architecture)

**Goal:** Push the architecture beyond the exemplar. Choose ONE path:

#### Path A: Cross-Domain Transfer
- [ ] Build ≥2 domain definitions and show they compose
- [ ] Demonstrate a problem that requires concepts from both domains
- [ ] Show the classifier correctly routes to concepts across domains
- [ ] Achieve ≥90% on a mixed-domain worksheet

#### Path B: Dynamic Learning
- [ ] Implement a learning loop: after solving, record success/failure per concept
- [ ] Use success rates to rank solvers when multiple candidates exist
- [ ] Implement fallback: when no solver is found, flag for human/LLM review
- [ ] Show the system improves over multiple runs on the same worksheet

#### Path C: LLM-Augmented Solving
- [ ] Add an LLM-based solver for proof and reasoning problems
- [ ] Implement structured LLM prompting that uses domain knowledge as context
- [ ] Show this solves problems that SymPy alone cannot (e.g., geometric reasoning, proofs)
- [ ] **Bonus:** Use the 5 challenge problems as your test set — Problems 2, 3, 5 all require multi-step proof reasoning that an LLM solver could handle

#### Path D: Multi-Format Pipeline
- [ ] Extend the ingestion stage to handle PDFs (text extraction + math OCR)
- [ ] Add image-based problem ingestion (Claude Vision or similar)
- [ ] Support Chinese input worksheets (not just Chinese output)
- [ ] Build an end-to-end demo: scan worksheet → auto-solve → PDF answer sheet

**Deliverable:** Working code + demo + architecture writeup + presentation

---

## Grading Rubric

| Level | Weight | Criteria |
|-------|--------|----------|
| L1 | 20% | Correct trace, clear understanding of architecture |
| L2 | 30% | Working new domain, ≥60% solve rate, clean definition |
| L3 | 25% | Knowledge enrichment, measurable improvement, ≥75% solve rate |
| L4 | 25% | Innovation quality, working demo, clear architectural contribution |

**Bonus points:**
- Clean, well-documented code (+5%)
- Chinese language support in output (+5%)
- Presentation/demo quality (+5%)
- Novel approach not listed above (+10%)

---

## Getting Started: Hints

1. **Start from the exemplar.** Don't reinvent the wheel — study what works and extend it.

2. **Knowledge sources matter more than code.** The exemplar's biggest improvements came from distilling instructor/pedagogy guides into domain knowledge, not from writing more Python.

3. **Classification is the targeting system.** If the wrong solver fires, you'll get wrong answers. Study how `calculus_limits.yaml` routes problems and test each rule carefully.

4. **Not all problems are computational.** Many homework questions ask "what is X?" or "give a counterexample." These need knowledge-based templates, not SymPy. The exemplar handles ~12 types of these.

5. **Work backwards from the end goal.** Pick a worksheet → identify which problems fail → figure out what domain knowledge would solve them → add it.

6. **Test incrementally.** After each addition, re-run the pipeline and check if your solve rate improved. Small, verified steps beat big, untested changes.

7. **Read the code, not just the docs.** The real architecture is in `solve.py`, `classify.py`, and `calculus_limits.yaml`. Everything else is supporting infrastructure.
