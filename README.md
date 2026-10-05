# C4C 提交成果 —— 作业自动求解与排版（国产大模型迁移版）

> 作者：lishengdan ｜ 挑战 ID：ch-20260717031447-k82c4m ｜ 2026-10-05

## 一句话总结

把 starter kit 的作业求解流水线从 Claude 迁移到 **DeepSeek**（兼容 Qwen/Kimi 一键切换），扩展 **线性代数 + 微分方程** 两个新学科和 **PDF/Word 摄入**，核心域准确率 **94.4%（持平 Claude 基线）→ 100%（LLM 兜底）**，新学科 8/8 + 4/4 全对，全程仅 **5 次 API 调用**（缓存后 0 成本）。

## 文件清单

| 文件 | 说明 |
|------|------|
| `lishengdan_C4C_方案设计.md` | 架构、国产模型选型（DeepSeek 及原因）、混合求解策略 |
| `lishengdan_C4C_homework-solver/` | 完整可运行技能包（五阶段流水线源码 + 测试作业 + 输出） |
| `lishengdan_C4C_作业原件.pdf` | 线性代数真实作业试卷（8 题，非微积分极限） |
| `lishengdan_C4C_作业原件_微分方程.md` | 微分方程作业原件（4 题） |
| `lishengdan_C4C_output.pdf` | 作业原件 → 流水线自动生成的解答 PDF（可提交版） |
| `lishengdan_C4C_验证报告.md` | 逐题标准答案对比（12+ 题）+ Claude 基线对比 + API 成本核算 |
| `lishengdan_C4C_教学说明.md` | 安装、使用、支持课程、FAQ |
| `lishengdan_C4C_AI日志.md` | AI 使用全过程记录（8 轮迭代、6 个坑）+ AAR 复盘 |
| `lishengdan_C4C_拿来说明.md` | 拿了什么/改了什么/Claude 版与国产模型版差异 |
| `输出PDF/` | 全部验证 PDF（Berkeley 基线 2 份 + 新学科 2 份 + 英文混合 1 份 + 作业原件） |

## 快速验证

```bash
cd lishengdan_C4C_homework-solver
pip install -r requirements.txt
python scripts/pipeline.py examples/linalg_homework_zh.md out/ --compile
# → 8/8 solved, homework.pdf
```

## 核心指标

| 指标 | 结果 |
|------|------|
| 微积分极限核心域（Berkeley 真题） | 18/18 = **100%**（Claude 基线 94.4%） |
| 线性代数（新学科，真实作业 PDF 链路） | **8/8 = 100%** |
| 微分方程（新学科） | **4/4 = 100%** |
| API 成本 | 首轮 5 次调用，重复运行 0 次 |
| PDF 产物 | 7 份，0 编译错误、0 未解析引用 |
