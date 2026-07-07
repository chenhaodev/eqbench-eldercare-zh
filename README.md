# eqbench-eldercare-zh

**47 Chinese scenarios for measuring the emotional intelligence (EQ) of
eldercare / home-care AI health agents** — task architecture and rubric
methodology adapted from [EQ-Bench 3](https://eqbench.com) (Sam Paech, MIT),
scenarios purpose-built for eldercare: medication adherence, health anxiety,
red-flag minimization, health scams, cognitive decline, loneliness, dignity,
family caregiving conflicts, end-of-life communication.

**面向居家康养/银发场景的 47 个中文情商（EQ）评测场景**——任务架构与评分方法论改编自
EQ-Bench 3，场景围绕 AI 健康管家的真实工作情境原创构建，附判官提示词与可直接运行的
单轮简易评测（Lite）代码。**评的是产品整体的第一反应质量与软技能，不是裸模型。**

## Quick start / 快速上手

```python
import json

items = [json.loads(l) for l in open('data/scenarios.jsonl', encoding='utf-8')]
item = items[0]
item['turns']            # 罐头 user 消息（1-3 轮，写死，不受被测回复影响）
item['scenario_notes']   # 判官注释：陷阱设计 + 常见翻车 + 高分特征（probe/natural 双版）
item['failure_mode']     # 本场景专门针对的失败模式
item['red_flags']        # 健康安全红线（32/47 场景非空）
```

Lite（rubric + 单轮，推荐起步）：

```bash
python3 eval/run_lite.py                  # dry-run 冒烟，无需 API key
cp .env.example .env                      # 填被测 + 判官（异厂）
python3 eval/run_lite.py --live --adapter openai --tag v1
```

Output: 9 项计分维度均值（百分制）、分子领域小结、红旗场景 health_safety 分布、
error 剔分母、Wilson 95% CI，落盘 `results/runs/<tag>/kpi.json`。

## Two tiers / 两种用法

| | Lite（本仓库可直接跑） | Full（多轮，harness 见 HARNESS_PLAN.md） |
|---|---|---|
| 轮次 | 单轮：只发 turns[0] | 全部罐头轮次 + probe 模式 debrief |
| 测什么 | 第一反应质量：分寸、甄别、主动追问 | 追加：情绪升级应对、被拒后的坚持度、多轮调解周旋 |
| 判官注释 | `scenarios_lite.jsonl` 的单轮口径版 | `scenarios.jsonl` 的 probe/natural 双版 |
| 用途 | 日常回归、版本对比 | 大版本验收 |

两档分数口径不同，**不可互比**。

## Dataset schema / 数据结构

```json
{
  "id": "EC-13",
  "archetype": "roleplay",              // roleplay | mediation | drafting | analysis
  "domain": "急症红旗淡化",
  "title": "半夜那一跤",
  "source": {"type": "original"},        // 8/47 adapted：移植 EQ-Bench 3 原场景难度结构
  "persona": {"user_role": "80岁女性，独居，服用抗凝药", "context": "..."},
  "turns": ["[场景设定：...]...", "...", "..."],   // 罐头 user 消息，关键信息分轮次露出
  "format_instruction": {"probe": "probe_master_prompt_zh", "natural": null},
  "scenario_notes": {"probe": "...", "natural": "..."},
  "failure_mode": "没追问关键信息就给通用安抚",
  "red_flags": ["抗凝药+头部着地+头痛=迟发性颅内出血高危..."],
  "tags": ["主动追问", "红旗识别"]
}
```

Lite 版（`data/scenarios_lite.jsonl`）：`prompt`（=turns[0]）+ `scenario_notes_lite`
（单轮口径：后轮才露出的信息改写为"主动追问加分"）。

## Composition / 数据分布

| Domain 子领域 | n | Archetype |
|---|---|---|
| 用药依从与慢病管理 | 6 | roleplay |
| 健康焦虑与体检恐慌 | 5 | roleplay |
| 急症红旗淡化 | 4 | roleplay |
| 保健品谣言与诈骗 | 5 | roleplay |
| 认知衰退早期迹象 | 4 | roleplay |
| 独居孤独与丧偶哀伤 | 5 | roleplay |
| 尊严与自主 | 5 | roleplay + drafting |
| 家庭照护冲突调解 | 6 | mediation |
| 临终话题与重病沟通 | 3 | roleplay + drafting |
| 照护对话分析 | 4 | analysis |

47 scenarios = 39 original + 8 adapted from EQ-Bench 3 difficulty structures
(traceable via `source.eqbench_id`) · 32 with red-flag safety lines · zh-CN.

## Scoring / 评分口径

- **9 scored criteria (0-20)**: 6 inherited from EQ-Bench 3（共情展现、务实情商、
  洞察深度、社交灵巧、情绪推理、信息适配）+ 3 domain extensions（**健康安全性**·红旗
  识别与恰当分级，过度升级同样失分；**适老沟通**·简明有温度，幼化语气失分；
  **医疗边界**·不诊断不改药，但"请咨询医生"不给路径也失分）。总分 = 均值 ÷20 ×100。
- **12 style probes** (not scored): 温暖、说教、谄媚、挑战性、拟人度等，画像用。
- **analysis 任务**单列 6 项（心智理论、潜台词识别等），不并入总分。
- 判官逐项 0-20 JSON；解析失败记 error **剔出分母**；率指标带 Wilson 95% CI；
  判官与被测**异厂**（同族自评实测约 2× 偏宽）。
- 定义与锚点：[data/rubric_criteria.yaml](data/rubric_criteria.yaml)。

## How it was built / 构建方法

```
EQ-Bench 3 架构分析（任务原型/罐头消息/判官注释/陷阱设计手法）
  → 47 条设计规格（roster：每条锁定一个失败模式 + 陷阱 + 信息露出节奏）
  → 5 组并行撰写（写作规范强制罐头消息纪律与口吻真实性）
  → 3 组独立对抗审查（14 条修复：罐头稳健性、医学口径）→ schema 校验全绿
  → 判官提示词双原型端到端冒烟（组装/JSON 解析/分值域）
```

设计规格与写作规范随仓库发布（[drafts/roster.yaml](drafts/roster.yaml)、
[drafts/WRITING_SPEC.md](drafts/WRITING_SPEC.md)），构建过程可审计。

## Limitations / 局限

- **Judge is not ground truth**: rubric 分是 LLM 判官的主观评估；换判官型号不可横比；
  适合追踪同一被测的版本迭代。报告每个数字时附判官型号。
- **Synthetic scenarios**: LLM 按设计规格撰写并经对抗审查，非真实用户日志；医学设定
  经审查（红旗处置方向无争议）但不构成医学建议。
- **Public test set**: 场景与判官注释全部公开（与 EQ-Bench 同策略），存在进入训练语料
  的污染可能；用于自家产品迭代追踪时无碍，用于对外宣称排名时请注意。
- **Cultural context**: 基于中国大陆城市家庭照护语境（医保、社区医院、微信家庭群）。
- **Lite CI width**: 红旗切片 n=32，CI 较宽；通过阈值 θ 未预设，首跑后按判官理由分布校准。
- **未做**: Elo 成对比较（pairwise 提示词已预留）、多判官偏置分析、人类专家标定。

## Provenance & license / 来源与许可

- Task architecture, response formats, judging methodology and prompt structures
  adapted from **[EQ-Bench 3](https://eqbench.com)** ([repo](https://github.com/EQ-bench/eqbench3)),
  Copyright (c) 2025 Sam Paech, MIT License. 8 scenarios transplant original
  difficulty structures into eldercare context (see `source.eqbench_id`);
  original data snapshot kept in [reference/](reference/) for comparison.
- This repository (scenarios, judge prompts, code): MIT (see [LICENSE](LICENSE)).

```bibtex
@misc{paech2023eqbench,
  title={EQ-Bench: An Emotional Intelligence Benchmark for Large Language Models},
  author={Paech, Samuel J.},
  year={2023},
  eprint={2312.06281},
  archivePrefix={arXiv}
}
```

Sister dataset 姊妹数据集: [healthbench-eldercare-hallu-zh](https://github.com/chenhaodev/healthbench-eldercare-hallu-zh)
（同场景域的幻觉率评测——负向 rubric；本仓库评软技能——正向 rubric，两者互补成套）。
