#!/usr/bin/env python3
"""ElderCare-EQ Full 多轮评测 runner（纯 stdlib）。

这是本数据集的完整形态：罐头 user 消息逐轮发送（信息分轮次露出、情绪升级、
施压摊牌），被测必须在多轮中保持追问、坚持与分寸——单轮 Lite 测不到的部分。

两种模式（--mode）：
  probe    turn1 套内省块格式指令（我的判断/对方在想/我的回复），场景结束后追加
           debrief 复盘轮；判官用 rubric_probe_zh。诊断信号最大。
  natural  罐头消息原样发送；判官用 rubric_natural_zh。最贴生产行为。

被测接入（--adapter）：mock（dry-run 默认）/ openai / claude-cli。
openai 指 OpenAI 兼容协议（DeepSeek/SiliconFlow 等国内 API 均可直连，非 OpenAI 厂商）；
claude-cli 仅冒烟自测（被测判官同族，分数不作正式口径）。
多轮状态：openai 走全量 messages 数组（无状态多轮）；claude-cli 拼接文本上下文。

用法：
  python3 eval/run_full.py                                          # dry-run 全量
  python3 eval/run_full.py --live --adapter openai --mode probe --tag v1-full   # 正式（.env 预设国内 API）
  python3 eval/run_full.py --live --adapter claude-cli --judge claude-cli --only EC-02  # 冒烟自测
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_lite import (  # noqa: E402
    ANALYSIS, PROBES, SCORED, TruncatedError, load_env_file, openai_chat, openai_request,
    output_format,
)
from wilson import wilson  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


# ── 多轮被测 adapter：输入 messages=[{role,content},...]，返回 assistant 文本 ──

def chat_mock(rec, messages):
    h = int(hashlib.sha256(f"{rec['id']}:{len(messages)}".encode()).hexdigest(), 16)
    return f"[mock 第{(len(messages) + 1) // 2}轮回复 {rec['id']} #{h % 1000}] 我想先确认几件事……"


def chat_claude_cli(rec, messages):
    model = os.environ.get("CANDIDATE_MODEL", "claude-haiku-4-5-20251001")
    convo = "\n\n".join(f"{m['role'].capitalize()}:\n{m['content']}" for m in messages)
    r = subprocess.run(["claude", "-p", "--model", model], input=convo + "\n\nAssistant:",
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI: {r.stderr[:300]}")
    return r.stdout.strip()


def chat_openai(rec, messages):
    body = openai_request(
        os.environ["CANDIDATE_BASE_URL"], os.environ["CANDIDATE_API_KEY"],
        {"model": os.environ["CANDIDATE_MODEL"], "temperature": 0.7, "max_tokens": 4096,
         "messages": [{"role": m["role"], "content": m["content"]} for m in messages]})
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        raise TruncatedError(choice["message"]["content"])
    msg = choice["message"]
    return msg.get("content") or msg.get("reasoning_content") or ""


ADAPTERS = {"mock": chat_mock, "claude-cli": chat_claude_cli, "openai": chat_openai}


# ── 组装与执行 ────────────────────────────────────────────

def tmpl(name):
    return (DATA / "candidate_prompts" / f"{name}.txt").read_text(encoding="utf-8")


def run_candidate(rec, mode, adapter_fn):
    """执行多轮对话，返回 (transcript_parts, debrief|None)。"""
    fi = rec["format_instruction"][mode]
    messages, parts = [], []
    for i, turn in enumerate(rec["turns"]):
        user_msg = tmpl(fi).replace("{scenario_prompt}", turn) if (i == 0 and fi) else turn
        messages.append({"role": "user", "content": user_msg})
        answer = adapter_fn(rec, messages)
        messages.append({"role": "assistant", "content": answer})
        parts.append(f"User:\n{user_msg}\n\nAssistant:\n{answer}")
    debrief = None
    if mode == "probe" and rec["archetype"] in ("roleplay", "mediation"):
        messages.append({"role": "user", "content": tmpl("probe_debrief_prompt_zh")})
        debrief = adapter_fn(rec, messages)
    return parts, debrief


def build_judge_prompt(rec, parts, debrief, mode):
    transcript = "\n\n---\n\n".join(parts)
    if rec["archetype"] == "analysis":
        t = (DATA / "judge_prompts" / "rubric_analysis_zh.txt").read_text(encoding="utf-8")
        keys = ANALYSIS
        prompt = t.replace("{transcript}", transcript)
    elif mode == "probe":
        t = (DATA / "judge_prompts" / "rubric_probe_zh.txt").read_text(encoding="utf-8")
        keys = SCORED + PROBES
        prompt = t.replace("{transcript}", transcript).replace("{debrief}", debrief or "（无复盘）")
    else:
        t = (DATA / "judge_prompts" / "rubric_natural_zh.txt").read_text(encoding="utf-8")
        keys = SCORED + PROBES
        prompt = t.replace("{transcript}", transcript)
    prompt = (prompt.replace("{scenario_notes}", rec["scenario_notes"][mode] or rec["scenario_notes"]["probe"])
              .replace("{output_format}", output_format(keys)))
    return prompt, keys


def judge_call(rec, judge_prompt, keys, args):
    if not args.live:
        scores = {"chain_of_thought_reasoning": "[mock 判官推理]"}
        for k in keys:
            h = int(hashlib.sha256(f"{rec['id']}:{k}:full".encode()).hexdigest(), 16)
            scores[k] = h % 21
        return scores
    if args.judge == "claude-cli":
        model = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5-20251001")
        r = subprocess.run(["claude", "-p", "--model", model], input=judge_prompt,
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"judge claude CLI: {r.stderr[:300]}")
        raw = r.stdout
    else:
        raw, _ = openai_chat(os.environ["JUDGE_BASE_URL"], os.environ["JUDGE_API_KEY"],
                             os.environ["JUDGE_MODEL"], judge_prompt,
                             temperature=0.0, max_tokens=int(os.environ.get("JUDGE_MAX_TOKENS", "6144")))
    start = raw.find("{")
    if start == -1:
        raise ValueError(f"判官输出无 JSON 对象（前120字: {raw[:120]!r}）")
    return json.loads(raw[start: raw.rfind("}") + 1])


def run_one(rec, args):
    adapter_fn = ADAPTERS["mock"] if not args.live else ADAPTERS[args.adapter]
    try:
        parts, debrief = run_candidate(rec, args.mode, adapter_fn)
    except TruncatedError:
        return {"id": rec["id"], "status": "truncated"}
    except Exception as e:
        return {"id": rec["id"], "status": "error", "stage": "candidate", "error": str(e)[:300]}

    judge_prompt, keys = build_judge_prompt(rec, parts, debrief, args.mode)
    for attempt in (1, 2):
        try:
            scores = judge_call(rec, judge_prompt, keys, args)
            missing = [k for k in keys if k not in scores]
            bad = [k for k in keys if not (isinstance(scores.get(k), (int, float)) and 0 <= scores[k] <= 20)]
            if missing or bad:
                raise ValueError(f"判官输出缺项/越界: missing={missing} bad={bad}")
            return {"id": rec["id"], "status": "ok", "archetype": rec["archetype"],
                    "domain": rec["domain"], "red_flags": bool(rec["red_flags"]),
                    "n_turns": len(rec["turns"]), "transcript": "\n\n---\n\n".join(parts),
                    "debrief": debrief, "scores": {k: scores[k] for k in keys},
                    "judge_reasoning": scores.get("chain_of_thought_reasoning", "")}
        except Exception as e:
            if attempt == 2:
                return {"id": rec["id"], "status": "error", "stage": "judge", "error": str(e)[:300]}


def aggregate(results, args):
    ok = [r for r in results if r["status"] == "ok"]
    main = [r for r in ok if r["archetype"] != "analysis"]
    ana = [r for r in ok if r["archetype"] == "analysis"]

    def mean(vals):
        return round(sum(vals) / len(vals), 2) if vals else None

    per_criterion = {k: mean([r["scores"][k] for r in main]) for k in SCORED} if main else {}
    per_domain = {}
    for r in main:
        per_domain.setdefault(r["domain"], []).append(sum(r["scores"][k] for k in SCORED) / len(SCORED))
    rf = [r for r in main if r["red_flags"]]
    rf_block = {"n": len(rf)}
    if args.redflag_theta is not None and rf:
        hits = sum(1 for r in rf if r["scores"]["health_safety"] >= args.redflag_theta)
        p, lo, hi = wilson(hits, len(rf))
        rf_block.update({"theta": args.redflag_theta, "pass_rate": p, "ci95": [lo, hi]})
    elif rf:
        hs = sorted(r["scores"]["health_safety"] for r in rf)
        rf_block["health_safety_distribution"] = {"min": hs[0], "median": hs[len(hs) // 2], "max": hs[-1]}

    return {
        "eval": "eldercare-eq-full",
        "mode": f"multi-turn {args.mode} + rubric",
        "adapter": args.adapter if args.live else "mock(dry-run)",
        "judge": (os.environ.get("JUDGE_MODEL", "claude-cli-default") if args.live else "mock(dry-run)"),
        "n_total": len(results), "n_ok": len(ok),
        "n_error": sum(1 for r in results if r["status"] == "error"),
        "n_truncated": sum(1 for r in results if r["status"] == "truncated"),
        "rubric_score_pct": (round(sum(per_criterion[k] for k in SCORED) / len(SCORED) / 20 * 100, 1)
                             if main else None),
        "per_criterion_mean": per_criterion,
        "analysis_score_pct": (round(sum(mean([r["scores"][k] for r in ana]) for k in ANALYSIS)
                                     / len(ANALYSIS) / 20 * 100, 1) if ana else None),
        "per_domain_mean": {d: round(sum(v) / len(v), 2) for d, v in sorted(per_domain.items())},
        "red_flag_scenarios": rf_block,
        "verdict": None,
        "caveat": (f"口径=Full 多轮 {args.mode}，分数与 Lite 单轮版及另一 mode 均不可比；"
                   "判官为 LLM 主观评估，换判官型号不可横比。"
                   f"数据=data/scenarios.jsonl n={len(results)}；error 已剔出分母。"),
        "command": " ".join(sys.argv),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--adapter", default="mock", choices=["mock", "claude-cli", "openai"])
    ap.add_argument("--judge", default="openai", choices=["openai", "claude-cli"])
    ap.add_argument("--mode", default="probe", choices=["probe", "natural"])
    ap.add_argument("--only", default="")
    ap.add_argument("--tag", default="dryrun-full")
    ap.add_argument("--redflag-theta", type=int, default=None)
    args = ap.parse_args()
    load_env_file()

    recs = [json.loads(l) for l in (DATA / "scenarios.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        recs = [r for r in recs if r["id"] in wanted]

    run_dir = ROOT / "results" / "runs" / args.tag
    run_dir.mkdir(parents=True, exist_ok=True)
    results_file = run_dir / "results.jsonl"
    done = set()
    if results_file.exists():
        # error 行不算完成：剔除后重写文件，重跑时自动补测（瞬时网络失败可自愈）
        kept = []
        for line in results_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["status"] == "error":
                continue
            kept.append(line)
            done.add(r["id"])
        results_file.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    with results_file.open("a", encoding="utf-8") as fh:
        for rec in recs:
            if rec["id"] in done:
                continue
            res = run_one(rec, args)
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"{res['id']}: {res['status']}")

    results = [json.loads(l) for l in results_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    kpi = aggregate(results, args)
    (run_dir / "kpi.json").write_text(json.dumps(kpi, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nKPI → {(run_dir / 'kpi.json').relative_to(ROOT)}")
    print(json.dumps({k: kpi[k] for k in ("n_ok", "n_error", "rubric_score_pct", "analysis_score_pct")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
