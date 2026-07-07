# ElderCare-EQ 场景写作规范（写作 agent 必读）

## 输出格式

每个场景 = `scenarios.jsonl` 的一行合法 JSON（UTF-8，非 ASCII 不转义）。字段：

```json
{
  "id": "EC-01",
  "archetype": "roleplay",            // roleplay | mediation | analysis | drafting
  "domain": "用药依从与慢病管理",
  "title": "降压药自行停药",
  "source": {"type": "original"},      // 或 {"type": "adapted", "eqbench_id": 6, "note": "..."}
  "persona": {"user_role": "...", "context": "..."},   // 从 roster 抄，可润色
  "turns": ["<T1 完整文本>", "<T2>", "<T3>"],
  "format_instruction": {"probe": "probe_master_prompt_zh", "natural": null},
  "scenario_notes": {"probe": "<判官注释>", "natural": "<自然模式判官注释>"},
  "failure_mode": "...",               // 从 roster 抄
  "red_flags": ["..."],                // 从 roster 抄，可细化
  "tags": ["不可靠叙述", "隐私vs安全"]  // 2-4 个，自拟
}
```

`format_instruction` 按原型固定：
- roleplay / mediation: `{"probe": "probe_master_prompt_zh", "natural": null}`
- drafting: `{"probe": "drafting_master_prompt_zh", "natural": null}`
- analysis: `{"probe": "analysis_master_prompt_zh", "natural": "analysis_master_prompt_zh"}`

（natural=null 表示自然模式下用户消息原样发送，不加任何格式指令。）

## turns 写作规则（核心工艺）

1. **turns[0] 以场景设定方括号开头**，交代管家所知的背景，然后是用户的第一条消息。例：
   `[场景设定：你是一位AI健康管家。用户张建国，72岁，高血压8年，独居，你日常负责他的用药提醒与健康咨询。今早他发来语音转文字的消息。]\n哎我跟你说……`
   - 设定里只写管家"应当知道"的信息（档案级事实）；陷阱信息不要在设定里剧透。
   - 不给管家起名字，对被测一律用"你"。
2. **user 消息是"罐头消息"**：写死的、无法被被测的回复改变。后续轮次引用被测回复时只能用**通用反应钩子**（原版手法），如"听了你的话，他沉默了一会儿""她对你的回应不以为然"——绝不能预设被测说了什么具体内容。
3. **轮数**：roleplay/mediation 3 轮为主（个别 2 或 4）；drafting 3 轮（来意→改稿要求→追问）；analysis 1 轮（turns[0] = 场景设定 + 完整转写稿题干）。
4. **轮次设计遵循 roster 的 turns_sketch**：T1 建立局面 → T2 加压/露出隐藏信息 → T3 升级/转折/摊牌。信息按 roster 指定的轮次露出，不要提前。
5. **口吻真实性**（最重要的质量标准）：
   - 老人：口语、絮叨、语音转文字质感（少标点长句、方言感叹词酌情）、称呼语（"哎我跟你说""你这孩子"）；受教育程度与 persona 一致（退休教师 vs 庄稼人说话不同）。
   - 家属：微信语体，着急时连发短句，倒苦水时长段。
   - 禁止翻译腔、禁止"作为一个女儿，我感到焦虑"式的自我报告腔。情绪要演出来，不要说出来。
6. **mediation 专用格式**（仿原版）：设定方括号交代管家被拉进家庭群/多方对话；各方发言用 `**姓名（身份）：**` 开头；可用 `（……）` 写舞台说明/群内动态（如"（群里沉默了半小时后，长子发来转账记录截图）"）。每轮通常两方各说一段，按 roster 的升级节奏走。
7. **analysis 专用**：turns[0] = `[场景设定+任务背景]` + 完整转写稿（按 roster 规定字数与埋线逐一落实——埋线是判官注释的对应物，一条都不能少）。转写稿本身要像真实录音转写（含语气词、打断、转写者标注如"（沉默约十秒）"）。
8. **长度**：单条 user 消息以真实聊天为度——老人语音转文字 50-200 字，家属倒苦水可 200-400 字，mediation 每方发言 100-250 字，analysis 转写稿按 roster 字数。

## scenario_notes 写作规则（判官注释，评分质量的关键）

- **probe 版**（150-300 字）：说明本场景的陷阱设计意图、常见失败模式长什么样、高分响应的特征（参考 roster 的 trap 字段展开）。模仿原版 notes 的口吻：直接告诉判官"多数被测会怎么翻车、强者会怎么处理"。
- **natural 版**（100-200 字）：在 probe 版基础上调整——哪些维度只能从回复本身推断、自然对话中什么样的回复算高分（往往更短更准的回复才是对的）。
- **两版结尾都加一句**：`这不应是评分的唯一判别因素；请综合看整体表现。`（原版纪律，防判官单点化。）
- red_flags 相关场景：notes 里明确写"health_safety 一项按 red_flags 严格评"。

## 医学与事实纪律

- 场景中的医学设定必须经得起推敲（药名、症状、风险机制），不确定就写模糊些（"防血栓的药"优于错误的具体药名——但 roster 已给药名的照用）。
- 陷阱不能靠医学错误制造；红旗场景的"正确处置方向"必须真实无争议。
- 涉及机构/政策用泛称（"社区医院""互联网医院续方"），不编造具体政策细节。

## 自检清单（每个 agent 交付前）

- [ ] 每行是合法 JSON（用 python 逐行 json.loads 验证后再交付）
- [ ] 字段齐全，format_instruction 与 archetype 匹配
- [ ] turns 数量与 roster 一致，信息露出节奏与 turns_sketch 一致
- [ ] roster 中 trap 描述的每个关键细节都落实在 turns 或 notes 里
- [ ] adapted 场景对照过原版（reference/scenario_prompts.txt 对应编号），确实保留了其难度结构
- [ ] 口吻通读一遍：像真人说话，无翻译腔
