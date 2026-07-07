#!/usr/bin/env python3
"""判官提示词端到端冒烟（纯 stdlib，被测/判官走 claude CLI headless）。

验证目标：candidate_prompts 模板可组装、多轮对话可走通、判官提示词产出可解析的
逐项 0-20 JSON。不产生正式评分（判官与被测同族且单轮，仅测机制）。

用法: python3 scripts/smoke_judge.py [--model claude-haiku-4-5-20251001] [--ids EC-45,EC-02]
产物: drafts/smoke/<id>.transcript.txt / <id>.judge.json
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "drafts" / "smoke"

SCORED = ["demonstrated_empathy", "pragmatic_ei", "depth_of_insight", "social_dexterity",
          "emotional_reasoning", "message_tailoring", "health_safety",
          "elder_communication", "medical_boundary"]
PROBES = ["boundary_setting", "safety_conscious", "moralising", "sycophantic", "compliant",
          "challenging", "warmth", "validating", "analytical", "reactive",
          "conversational", "humanlike"]
ANALYSIS = ["depth_of_insight", "emotional_reasoning", "theory_of_mind",
            "subtext_identification", "intellectual_grounding", "correctness"]


def llm(prompt, model, timeout=300):
    r = subprocess.run(["claude", "-p", "--model", model], input=prompt,
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI 失败: {r.stderr[:500]}")
    return r.stdout.strip()


def parse_json(text):
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def output_format(keys):
    return json.dumps({"chain_of_thought_reasoning": "对各项评分的批判性推理",
                       **{k: 0 for k in keys}}, ensure_ascii=False, indent=2)


def run_scenario(rec, model):
    tmpl_dir = DATA / "candidate_prompts"
    probe_tmpl = rec["format_instruction"]["probe"]
    master = (tmpl_dir / f"{probe_tmpl}.txt").read_text(encoding="utf-8")

    if rec["archetype"] == "analysis":
        prompt = master.replace("{scenario_prompt}", rec["turns"][0])
        answer = llm(prompt, model)
        transcript = f"User:\n{prompt}\n\nAssistant:\n{answer}"
        judge_tmpl = (DATA / "judge_prompts" / "rubric_analysis_zh.txt").read_text(encoding="utf-8")
        judge_prompt = (judge_tmpl.replace("{transcript}", transcript)
                        .replace("{scenario_notes}", rec["scenario_notes"]["probe"])
                        .replace("{output_format}", output_format(ANALYSIS)))
        expected = ANALYSIS
    else:
        # 多轮 probe：首轮套 master 模板，后续轮原样，最后 debrief
        convo, transcript_parts = [], []
        for i, turn in enumerate(rec["turns"]):
            user_msg = master.replace("{scenario_prompt}", turn) if i == 0 else turn
            convo.append(f"User:\n{user_msg}")
            answer = llm("\n\n".join(convo) + "\n\nAssistant:", model)
            convo.append(f"Assistant:\n{answer}")
            transcript_parts.append(f"User:\n{user_msg}\n\nAssistant:\n{answer}")
        debrief_q = (tmpl_dir / "probe_debrief_prompt_zh.txt").read_text(encoding="utf-8")
        convo.append(f"User:\n{debrief_q}")
        debrief = llm("\n\n".join(convo) + "\n\nAssistant:", model)
        transcript = "\n\n---\n\n".join(transcript_parts)
        judge_tmpl = (DATA / "judge_prompts" / "rubric_probe_zh.txt").read_text(encoding="utf-8")
        judge_prompt = (judge_tmpl.replace("{transcript}", transcript)
                        .replace("{debrief}", debrief)
                        .replace("{scenario_notes}", rec["scenario_notes"]["probe"])
                        .replace("{output_format}", output_format(SCORED + PROBES)))
        expected = SCORED + PROBES

    judge_raw = llm(judge_prompt, model)
    scores = parse_json(judge_raw)

    missing = [k for k in expected if k not in scores]
    bad = {k: v for k, v in scores.items()
           if k != "chain_of_thought_reasoning" and not (isinstance(v, (int, float)) and 0 <= v <= 20)}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{rec['id']}.transcript.txt").write_text(transcript, encoding="utf-8")
    (OUT / f"{rec['id']}.judge.json").write_text(
        json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")

    status = "PASS" if not missing and not bad else f"FAIL missing={missing} bad={bad}"
    shown = {k: scores.get(k) for k in expected[:6]}
    print(f"{rec['id']} [{rec['archetype']}]: {status}\n  样例分数: {shown}")
    return not missing and not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--ids", default="EC-45,EC-02")
    args = ap.parse_args()

    recs = {json.loads(l)["id"]: json.loads(l)
            for l in (DATA / "scenarios.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    ok = True
    for sid in args.ids.split(","):
        ok &= run_scenario(recs[sid.strip()], args.model)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
