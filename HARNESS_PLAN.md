# ElderCare-EQ 评测 Harness 计划（v0.2 · 大部分已落地）

> 状态更新：P0 已交付并超额——多轮 runner `eval/run_full.py`（probe/natural 双模式、
> dry-run mock、断点续跑、error 剔分母）与单轮 `eval/run_lite.py` 都可直接跑，
> claude-cli 通道 live 冒烟通过。**剩余待办**：真管家接入（§3 的 B/C adapter，等接入
> 4 问的答案）、多迭代稳分（P3）、Elo 成对比较。以下原计划保留作设计依据。

## 1. 目标与范围

对用户的 **AI 健康管家智能体**跑 ElderCare-EQ 数据集（47 场景），产出：
每场景逐项 0-20 分 → 子领域/维度聚合 → 单一 KPI 文件（含置信区间与 caveat）→ 可读报告。

本期做 rubric 绝对分（版本迭代追踪用）；Elo 成对比较、基线模型对照仍不在范围（提示词已预留，架构留槽）。

## 2. 架构总览

```
eval/
├── run_eval.py            # 主 runner（纯 stdlib，无三方依赖）
├── adapters.py            # ★ 被测接入层（唯一等待用户决策的文件）
├── judge.py               # 判官调用 + JSON 健壮解析 + 重试
├── assemble.py            # 提示词组装（双轨/四原型，从 smoke_judge.py 提炼）
├── stats.py               # Wilson CI、聚合、KPI 生成（复用 eval-forge wilson.py）
└── mock.py                # dry-run 确定性 mock（hash(case_id) 派生）
results/
├── runs/<tag>/results.jsonl   # 逐场景落盘（断点续跑依据）
└── kpi.yaml                   # 单一真相源：分数只进这里
```

### 数据流（每场景一次评测）

```
scenarios.jsonl 单条
  → assemble：按 archetype+mode 组装首轮提示词（模板已交付于 data/candidate_prompts/）
  → adapter：多轮调用被测（罐头 user 消息按 turns 顺序发送；probe 模式末尾加 debrief 轮）
  → judge：对应判官提示词 + transcript + scenario_notes + output_format → 逐项 0-20 JSON
  → parse/validate：缺项/越界/解析失败 → status=error，剔出分母（绝不降级为 0 分）
  → append results.jsonl（已评过的场景跳过 = 断点续跑）
```

## 3. 被测接入层（adapters.py）——等待用户的唯一决策

统一接口：`class Candidate: def chat(self, messages: list[dict], scenario_meta: dict) -> str`

| 模式 | 适用 | 实现量 |
|---|---|---|
| A. `OpenAICompatAdapter` | 管家暴露 OpenAI 格式 chat/completions | ~30 行（urllib，env 配 BASE_URL/KEY/MODEL） |
| B. `CustomHTTPAdapter` | 自有 HTTP 协议（如带 user_id/session 的对话接口） | ~50 行，需要用户提供：endpoint、鉴权、请求/响应字段、**会话如何保持**（多轮是靠 messages 数组还是 server 端 session_id） |
| C. `ReplayAdapter` | 管家不便被程序调用：人工/半自动导出对话记录，harness 只做判官侧 | ~20 行（读 transcripts 目录） |
| D. `ClaudeCLIAdapter` | 冒烟/自测用（smoke_judge.py 已验证该路径） | 已有雏形 |

**需要用户回答的问题（定 A/B/C 其一即可开工）：**
1. 管家怎么调？（URL + 鉴权方式 + 一个 curl 示例最佳）
2. 多轮状态怎么带？（每次全量 messages / server 端会话 id / 其他）
3. 管家有无自己的 system prompt / 人设注入？（评测时保留——评的是产品整体，不是裸模型）
4. 有无速率/并发限制？（决定 runner 串行还是小并发）

**其它一切不阻塞**：judge.py、assemble.py、stats.py、mock.py 都不依赖接入方式，可先行开发并用 D 模式全链路验证。

## 4. 判官层（judge.py）

- **异厂纪律**（eval-forge ④）：判官必须与管家底座模型**不同厂**。角色键配置：`JUDGE_BASE_URL / JUDGE_API_KEY / JUDGE_MODEL`，OpenAI 兼容协议一网打尽（OpenRouter/DeepSeek/Gemini `…/openai` 端点均可）。结果记录判官型号。
- temperature=0.0，max_tokens 给足（判官要输出 chain_of_thought + 21 项分数）。
- 解析：`json.loads(out[out.find("{"):out.rfind("}")+1])`，失败重试 1 次，再失败记 error。
- 截断分列（eval-forge ⑤）：被测回复 `finish_reason==length` 单独标 `n_truncated`，与质量失败分开报。

## 5. 运行特性（继承 eval-forge ⑥）

- `--dry-run`（默认）：mock 判官分数由 `hash(scenario_id+criterion)` 确定性派生，无网络全绿，可 diff。
- `--live`：真跑。`--only EC-02,EC-12`：子集。`--tag v0.3-probe`：结果另存。`--mode probe|natural`：双轨选择。`--iterations n`：多迭代取均值。
- 断点续跑：逐场景 append，重跑跳过已判；删 results.jsonl 才重来。
- 成本估算：47 场景 × (3-4 轮被测 + 1 判官长调用) ≈ 判官侧 5-8 万 token/迭代；OpenRouter 上约 $1-3/迭代（取决于判官型号），5 迭代 $5-15 —— 与原版 rubric-only 成本同量级。

## 6. 统计与产出（stats.py → kpi.yaml）

- **总分**：9 计分项均值 ÷20 ×100（百分制）；analysis 场景用 6 项版，**单独聚合不并入总分**（口径不同：锚点是学术洞察力）。
- **分维度**：9 项各自均值 + 分布；12 探针项只报画像不聚合。
- **分子领域**：10 个 domain 各自小结——这是给用户看"管家哪类场景弱"的主视图。
- **红旗通过率**：32 个红旗场景中 `health_safety ≥ θ` 的比例，报 **Wilson 95% CI 下界**（唯一的比例类硬指标，n=32 CI 会宽，caveat 写明）。阈值 θ 不预设：P2 首跑后人工抽读 5-8 条判官理由，对照"放过红旗/恰当升级"的实际分布再定（避免拍脑袋阈值制造口径产物）。
- **verdict 三档**：下限/目标/挑战（阈值跑通 v1 后与用户一起定，先占位 null——禁手填）。
- kpi.yaml 每个 metric 块带：actual / ci95 / n / n_error / n_truncated / judge_model / mode / caveat / command（可复跑命令）。数字**只进这一处**，README 不复制。

## 7. 分阶段执行

| 阶段 | 内容 | 出口判据 |
|---|---|---|
| P0 | assemble/judge/mock/stats + runner 骨架；D 模式全链路 | `--dry-run` 47 场景全绿；D 模式 `--live --only EC-02,EC-45` 复现冒烟结果 |
| P1 | 用户定接入 → 写对应 adapter | `--only` 3 个场景真跑，transcript 人工抽读确认管家行为正常（含多轮状态正确传递） |
| P2 | 全量首跑（建议 probe 模式先行，判官信号大） | 47 场景 error 率 <5%；kpi.yaml 产出首批数字 |
| P3 | 稳定性：同配置重跑 1 次对比翻转率；若单项波动 >±1.5 → `--iterations 3` 起步 | 分数复现性有数据，caveat 写实 |
| P4（可选） | natural 模式对照跑；报告页（HTML，按 domain×criterion 热力图） | 双轨差值本身就是发现（格式遵循力 vs 自然表现） |

## 8. 风险与预案

- **管家有自己的多轮记忆/工具调用**：罐头消息假设"user 不受被测影响"，但管家若主动追问，罐头 T2 可能答非所问——场景已按"通用反应钩子"写作来兜底；P1 抽读重点验证这一点，若个别场景仍冲突，记 `scenario_incompat` 单列，不硬评。
- **判官格式漂移**（换判官型号后 JSON 不稳）：mock 先行 + 解析健壮截取 + error 剔分母，已兜。
- **额度/中断**：断点续跑已设计；真跑烧 API 前先 dry-run 确认全链路。
- **管家底座与判官同族**：P1 时问清管家底座厂商，选判官时避开；若不可避，加第二判官抽检 20% 对照，披露偏置。

---
*方法论依据：eval-forge（dry-run mock/断点续跑/Wilson CI/异厂判官/诚实纪律）；接口与占位符约定见 README「接入指引」；judge 组装逻辑的参考实现是 scripts/smoke_judge.py。*
