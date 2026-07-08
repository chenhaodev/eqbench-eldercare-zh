# Baselines · 基线参考结果

供接入自家 agent 时对照的公开基线跑分。每个目录含 `kpi.json`（聚合）与
`results.jsonl`（逐场景 transcript + 判官逐项分与理由，可审计）。

> 口径提醒：Lite 与 Full、probe 与 natural 各自独立口径，**互不可比**；
> 分数是"该被测 × 该判官"的组合产物，换判官不可横比（kpi.json 内 caveat 有声明）。

## qwen3-8b（演示被测 · 小模型下限参考）

- 被测：`Qwen/Qwen3-8B` @ SiliconFlow（temp 0.7）
- 判官：`deepseek-v4-pro` @ DeepSeek（temp 0.0，异厂）
- 时间：2026-07 · 单次迭代（n=1，未做多迭代稳分，分数波动 ±1-2 属正常）

| | Lite 单轮 | Full 多轮 probe |
|---|---|---|
| rubric_score_pct | 38.3 | 49.9 |
| analysis_score_pct | 54.2 | 63.7 |
| n_ok / n_error | 47 / 0 | 47 / 0 |
| 红旗 health_safety 中位数 | 5 / 20 | 4 / 20 |

**读数要点**（小模型的能力画像，与设计预期一致）：

- **红旗抓不住**：31 个红旗场景 health_safety 中位数仅 4-5 分（min 0-2）——
  能背"请咨询医生"（medical_boundary ~12）但识别不了"抗凝药+头部外伤"级别的危险组合。
- **probe 模式加成**：Full probe 的 depth_of_insight 12.3 vs Lite 6.1——内省块把
  小模型"想得到但第一句话说不出来"的部分显性化了；生产行为更接近 Lite/natural 口径。
- **弱项领域**：Lite 下家庭调解 5.1、健康焦虑 6.0 垫底；Full 下独居孤独 7.5 垫底。

对比锚点（非正式）：`deepseek-chat` 在 EC-13/16/06 抽测中 Lite ≈ 72、Full probe ≈ 72，
显著高于 Qwen3-8B 同场景——判别力方向正确。
