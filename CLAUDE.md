# eqbench-eldercare-zh · 仓库约定

银发居家健康 EQ 评测数据集（EQ-Bench 3 改编）+ 双档 runner。已发布：
GitHub chenhaodev/eqbench-eldercare-zh + HF datasets/chenhaodev/eqbench-eldercare-zh。

## 不可破坏的纪律

- **场景是罐头消息**：turns 里的 user 消息写死，后续轮引用被测回复只能用通用反应钩子
  （"听了你的话他不耐烦起来"）。改任何场景前读 `drafts/WRITING_SPEC.md`，改完必须过
  双极端思想实验（全顺从/强硬升级回复下每轮仍成立）。
- **改 scenarios*.jsonl 后必跑** `python3 scripts/validate.py` 与 `--lite`，全绿才能提交。
- **判官注释自包含**：notes 只能引用判官提示词实际注入的内容（红旗实质要内联复述，
  不能写"按 red_flags 字段评"——判官看不到该字段）。
- **多 agent 并行改数据**：产补丁文件由主会话串行合并，绝不并发读-改-写同一 jsonl。
- **口径互不可比**：Lite/Full、probe/natural、不同判官的分数不能横比；kpi 的 caveat 必须如实。

## 常用命令

```bash
python3 scripts/validate.py [--lite]      # 数据校验
python3 eval/run_full.py                  # dry-run（零配置，改 runner 后必跑）
python3 eval/run_lite.py --live --adapter openai --tag <tag>   # 真跑（.env 需 6 变量）
```

- runner 特性：断点续跑（error 行自动剔除补测）、网络重试、error 剔分母。
- `.env` 本地不入库；预设=被测 SiliconFlow Qwen / 判官 DeepSeek（异厂纪律）。
- 结果：`results/runs/<tag>/`（gitignored 草稿）；要发布的挑进 `results/baselines/`（入库）。

## 发布

- GitHub：正常 git push。
- HF：`HF_ENDPOINT=https://huggingface.co python3 scripts/push_hf.py`
  ——本机全局 HF_ENDPOINT 指向 hf-mirror（只读镜像），不覆盖会报"Invalid user token"。
- README 是 GitHub 版（无 frontmatter）；HF 版由 push_hf.py 自动拼 `dataset_card.yaml`。

## 背景文档

设计规格 `drafts/roster.yaml` · 写作规范 `drafts/WRITING_SPEC.md` ·
多轮 harness 计划 `HARNESS_PLAN.md` · Lite 设计 `LITE_PLAN.md` ·
方法论 skill：`/bench-transplant`（语料构造）、`/eval-forge`（评分统计）。
