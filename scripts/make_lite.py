#!/usr/bin/env python3
"""从 data/scenarios.jsonl 机械派生 Lite 单轮版 data/scenarios_lite.jsonl。

Lite 形态：只取 turns[0]，natural 模式（roleplay/mediation 无格式指令；
analysis/drafting 沿用各自任务指令模板）。scenario_notes.lite 若已存在则保留
（重跑不覆盖注释工作），否则置空占位，由后续 agent 填充。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "scenarios.jsonl"
DST = ROOT / "data" / "scenarios_lite.jsonl"

LITE_TEMPLATE = {  # archetype -> 单轮格式指令模板（None = 原样发送）
    "roleplay": None,
    "mediation": None,
    "drafting": "drafting_master_prompt_zh",
    "analysis": "analysis_master_prompt_zh",
}


def main():
    existing_notes = {}
    if DST.exists():
        for line in DST.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("scenario_notes_lite"):
                    existing_notes[r["id"]] = r["scenario_notes_lite"]

    out = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        lite = {
            "id": r["id"],
            "archetype": r["archetype"],
            "domain": r["domain"],
            "title": r["title"],
            "source": r["source"],
            "persona": r["persona"],
            "prompt": r["turns"][0],
            "format_instruction": LITE_TEMPLATE[r["archetype"]],
            "scenario_notes_lite": existing_notes.get(r["id"], ""),
            "failure_mode": r["failure_mode"],
            "red_flags": r["red_flags"],
            "tags": r["tags"],
        }
        out.append(json.dumps(lite, ensure_ascii=False))

    DST.write_text("\n".join(out) + "\n", encoding="utf-8")
    kept = len(existing_notes)
    print(f"写入 {len(out)} 条 → {DST.relative_to(ROOT)}（保留已有 lite 注释 {kept} 条）")


if __name__ == "__main__":
    main()
