#!/usr/bin/env python3
"""ElderCare-EQ Lite 单轮评测 runner（纯 stdlib）。

流程：scenarios_lite.jsonl 逐条 → 被测 adapter 单次调用 → rubric 判官（异厂建议）
→ 逐项 0-20 JSON → results/runs/<tag>/results.jsonl（断点续跑）→ kpi.yaml 聚合。

默认 dry-run（hash 派生确定性 mock，无网络全绿）；--live 真跑。

被测接入（--adapter）：
  mock       dry-run 专用（默认）
  claude-cli 本机 claude CLI headless（自测/冒烟）
  openai     OpenAI 兼容 API：env CANDIDATE_BASE_URL / CANDIDATE_API_KEY / CANDIDATE_MODEL
  replay     离线回放：--replay-dir 下每场景一个 <id>.txt（管家回复文本）

判官（--live 时必需）：env JUDGE_BASE_URL / JUDGE_API_KEY / JUDGE_MODEL（OpenAI 兼容协议），
或 --judge claude-cli 用本机 claude CLI 充当判官（冒烟用；正式评测请配异厂判官）。

用法示例：
  python3 eval/run_lite.py                                    # dry-run 全量
  python3 eval/run_lite.py --live --adapter claude-cli --judge claude-cli --only EC-02,EC-13
  python3 eval/run_lite.py --live --adapter openai --tag v0.3
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wilson import wilson  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SCORED = ["demonstrated_empathy", "pragmatic_ei", "depth_of_insight", "social_dexterity",
          "emotional_reasoning", "message_tailoring", "health_safety",
          "elder_communication", "medical_boundary"]
PROBES = ["boundary_setting", "safety_conscious", "moralising", "sycophantic", "compliant",
          "challenging", "warmth", "validating", "analytical", "reactive",
          "conversational", "humanlike"]
ANALYSIS = ["depth_of_insight", "emotional_reasoning", "theory_of_mind",
            "subtext_identification", "intellectual_grounding", "correctness"]


def load_env_file():
    """零依赖 .env 加载（真实 env 优先）。"""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ── 被测 adapter ──────────────────────────────────────────

def candidate_mock(rec, prompt):
    h = int(hashlib.sha256(rec["id"].encode()).hexdigest(), 16)
    return f"[mock 回复 {rec['id']} #{h % 1000}] 我先确认一下您现在的情况……"


def candidate_claude_cli(rec, prompt):
    model = os.environ.get("CANDIDATE_MODEL", "claude-haiku-4-5-20251001")
    r = subprocess.run(["claude", "-p", "--model", model], input=prompt,
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI: {r.stderr[:300]}")
    return r.stdout.strip()


def openai_chat(base_url, api_key, model, prompt, temperature=0.7, max_tokens=2048):
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "temperature": temperature, "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.load(resp)
    choice = body["choices"][0]
    msg = choice["message"]
    # 混合思考模型（如 Qwen3.x）偶发把全部输出放进 reasoning_content、content 为空——回退取之
    content = msg.get("content") or msg.get("reasoning_content") or ""
    return content, choice.get("finish_reason", "")


def candidate_openai(rec, prompt):
    text, finish = openai_chat(os.environ["CANDIDATE_BASE_URL"], os.environ["CANDIDATE_API_KEY"],
                               os.environ["CANDIDATE_MODEL"], prompt)
    if finish == "length":
        raise TruncatedError(text)
    return text


class TruncatedError(Exception):
    pass


def candidate_replay(rec, prompt, replay_dir):
    f = Path(replay_dir) / f"{rec['id']}.txt"
    if not f.exists():
        raise FileNotFoundError(f"replay 文件缺失: {f}")
    return f.read_text(encoding="utf-8").strip()


# ── 判官 ──────────────────────────────────────────────────

def output_format(keys):
    return json.dumps({"chain_of_thought_reasoning": "对各项评分的批判性推理",
                       **{k: 0 for k in keys}}, ensure_ascii=False, indent=2)


def build_judge_prompt(rec, answer):
    if rec["archetype"] == "analysis":
        tmpl = (DATA / "judge_prompts" / "rubric_analysis_zh.txt").read_text(encoding="utf-8")
        keys = ANALYSIS
    else:
        tmpl = (DATA / "judge_prompts" / "rubric_natural_zh.txt").read_text(encoding="utf-8")
        keys = SCORED + PROBES
    transcript = f"User:\n{assemble_prompt(rec)}\n\nAssistant:\n{answer}"
    return (tmpl.replace("{transcript}", transcript)
            .replace("{scenario_notes}", rec["scenario_notes_lite"])
            .replace("{output_format}", output_format(keys))), keys


def judge_mock(rec, judge_prompt, keys):
    scores = {"chain_of_thought_reasoning": "[mock 判官推理]"}
    for k in keys:
        h = int(hashlib.sha256(f"{rec['id']}:{k}".encode()).hexdigest(), 16)
        scores[k] = h % 21
    return scores


def judge_llm(judge_prompt, keys, judge_mode):
    if judge_mode == "claude-cli":
        model = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5-20251001")
        r = subprocess.run(["claude", "-p", "--model", model], input=judge_prompt,
                           capture_output=True, text=True, timeout=300)
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


# ── 组装 ──────────────────────────────────────────────────

def assemble_prompt(rec):
    if rec["format_instruction"]:
        tmpl = (DATA / "candidate_prompts" / f"{rec['format_instruction']}.txt").read_text(encoding="utf-8")
        return tmpl.replace("{scenario_prompt}", rec["prompt"])
    return rec["prompt"]


# ── 主流程 ────────────────────────────────────────────────

def run_one(rec, args):
    prompt = assemble_prompt(rec)
    try:
        if not args.live:
            answer = candidate_mock(rec, prompt)
        elif args.adapter == "claude-cli":
            answer = candidate_claude_cli(rec, prompt)
        elif args.adapter == "openai":
            answer = candidate_openai(rec, prompt)
        elif args.adapter == "replay":
            answer = candidate_replay(rec, prompt, args.replay_dir)
        else:
            answer = candidate_mock(rec, prompt)
    except TruncatedError:
        return {"id": rec["id"], "status": "truncated"}
    except Exception as e:
        return {"id": rec["id"], "status": "error", "stage": "candidate", "error": str(e)[:300]}

    judge_prompt, keys = build_judge_prompt(rec, answer)
    for attempt in (1, 2):
        try:
            scores = (judge_mock(rec, judge_prompt, keys) if not args.live
                      else judge_llm(judge_prompt, keys, args.judge))
            missing = [k for k in keys if k not in scores]
            bad = [k for k in keys if not (isinstance(scores.get(k), (int, float)) and 0 <= scores[k] <= 20)]
            if missing or bad:
                raise ValueError(f"判官输出缺项/越界: missing={missing} bad={bad}")
            return {"id": rec["id"], "status": "ok", "archetype": rec["archetype"],
                    "domain": rec["domain"], "red_flags": bool(rec["red_flags"]),
                    "answer": answer, "scores": {k: scores[k] for k in keys},
                    "judge_reasoning": scores.get("chain_of_thought_reasoning", "")}
        except Exception as e:
            if attempt == 2:
                return {"id": rec["id"], "status": "error", "stage": "judge", "error": str(e)[:300]}


def aggregate(results, args):
    ok = [r for r in results if r["status"] == "ok"]
    n_error = sum(1 for r in results if r["status"] == "error")
    n_trunc = sum(1 for r in results if r["status"] == "truncated")
    main = [r for r in ok if r["archetype"] != "analysis"]
    ana = [r for r in ok if r["archetype"] == "analysis"]

    def mean(vals):
        return round(sum(vals) / len(vals), 2) if vals else None

    per_criterion = {k: mean([r["scores"][k] for r in main]) for k in SCORED} if main else {}
    rubric_score = (round(sum(per_criterion[k] for k in SCORED) / len(SCORED) / 20 * 100, 1)
                    if main else None)
    analysis_score = (round(sum(mean([r["scores"][k] for r in ana]) for k in ANALYSIS) / len(ANALYSIS) / 20 * 100, 1)
                      if ana else None)
    per_domain = {}
    for r in main:
        per_domain.setdefault(r["domain"], []).append(
            sum(r["scores"][k] for k in SCORED) / len(SCORED))
    per_domain = {d: round(sum(v) / len(v), 2) for d, v in sorted(per_domain.items())}

    rf = [r for r in main if r["red_flags"]]
    theta = args.redflag_theta
    rf_block = {"n": len(rf), "theta": theta, "note": "θ 未校准前只报分布，不报通过率"}
    if theta is not None and rf:
        hits = sum(1 for r in rf if r["scores"]["health_safety"] >= theta)
        p, lo, hi = wilson(hits, len(rf))
        rf_block = {"n": len(rf), "theta": theta, "pass_rate": p, "ci95": [lo, hi],
                    "ci95_lower": lo}
    elif rf:
        hs = sorted(r["scores"]["health_safety"] for r in rf)
        rf_block["health_safety_distribution"] = {
            "min": hs[0], "median": hs[len(hs) // 2], "max": hs[-1]}

    return {
        "eval": "eldercare-eq-lite",
        "mode": "single-turn natural + rubric",
        "adapter": args.adapter if args.live else "mock(dry-run)",
        "judge": (os.environ.get("JUDGE_MODEL", "claude-cli-default") if args.live else "mock(dry-run)"),
        "n_total": len(results), "n_ok": len(ok), "n_error": n_error, "n_truncated": n_trunc,
        "rubric_score_pct": rubric_score,
        "per_criterion_mean": per_criterion,
        "analysis_score_pct": analysis_score,
        "per_domain_mean": per_domain,
        "red_flag_scenarios": rf_block,
        "verdict": None,
        "caveat": ("口径=Lite 单轮 natural，分数与全量多轮版不可比；判官为 LLM 主观评估，"
                   "换判官型号不可横比；dry-run 结果为 mock，仅验机制。"
                   f"数据=data/scenarios_lite.jsonl n={len(results)}；error 已剔出分母。"),
        "command": " ".join(sys.argv),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="真跑（默认 dry-run mock）")
    ap.add_argument("--adapter", default="mock",
                    choices=["mock", "claude-cli", "openai", "replay"])
    ap.add_argument("--judge", default="openai", choices=["openai", "claude-cli"])
    ap.add_argument("--replay-dir", default=str(ROOT / "replay"))
    ap.add_argument("--only", default="", help="逗号分隔场景 id 子集")
    ap.add_argument("--tag", default="dryrun")
    ap.add_argument("--redflag-theta", type=int, default=None,
                    help="红旗通过阈值（未校准前勿设，只报分布）")
    args = ap.parse_args()
    load_env_file()

    recs = [json.loads(l) for l in (DATA / "scenarios_lite.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        recs = [r for r in recs if r["id"] in wanted]

    missing_notes = [r["id"] for r in recs if not r["scenario_notes_lite"]]
    if missing_notes and args.live:
        sys.exit(f"FATAL: {len(missing_notes)} 条缺 lite 判官注释（{missing_notes[:5]}…），先完成注释再 --live")

    run_dir = ROOT / "results" / "runs" / args.tag
    run_dir.mkdir(parents=True, exist_ok=True)
    results_file = run_dir / "results.jsonl"
    done = set()
    if results_file.exists():
        for line in results_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])

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
    kpi_file = run_dir / "kpi.json"
    kpi_file.write_text(json.dumps(kpi, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nKPI → {kpi_file.relative_to(ROOT)}")
    print(json.dumps({k: kpi[k] for k in ("n_ok", "n_error", "rubric_score_pct", "analysis_score_pct")},
                     ensure_ascii=False))
    if kpi["n_error"] > len(results) * 0.05:
        sys.exit(f"WARN: error 率 {kpi['n_error']}/{len(results)} 超 5%")


if __name__ == "__main__":
    main()
