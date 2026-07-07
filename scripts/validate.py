#!/usr/bin/env python3
"""ElderCare-EQ 数据集校验（纯 stdlib）。

用法:
    python3 scripts/validate.py [scenarios.jsonl 路径, 默认 data/scenarios.jsonl]

检查项:
  schema      每条记录字段齐全、类型正确、枚举值合法
  id          id 唯一、格式 EC-NN、按序
  turns       轮数在原型允许范围内; analysis 必须单轮; turns[0] 含场景设定方括号
  format      format_instruction 与 archetype 匹配, 模板文件真实存在
  notes       scenario_notes 双轨齐全且以规定句结尾
  quota       各 domain 数量与设计矩阵一致
  criteria    rubric_criteria.yaml 中计分/探针/analysis 项数量与判官提示词引用一致
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ARCHETYPES = {"roleplay", "mediation", "analysis", "drafting"}

# 设计矩阵：domain -> (数量, 允许的原型集合)
QUOTA = {
    "用药依从与慢病管理": (6, {"roleplay"}),
    "健康焦虑与体检恐慌": (5, {"roleplay"}),
    "急症红旗淡化": (4, {"roleplay"}),
    "保健品谣言与诈骗": (5, {"roleplay"}),
    "认知衰退早期迹象": (4, {"roleplay"}),
    "独居孤独与丧偶哀伤": (5, {"roleplay"}),
    "尊严与自主": (5, {"roleplay", "drafting"}),
    "家庭照护冲突调解": (6, {"mediation"}),
    "临终话题与重病沟通": (3, {"roleplay", "drafting"}),
    "照护对话分析": (4, {"analysis"}),
}

FORMAT_BY_ARCHETYPE = {
    "roleplay": {"probe": "probe_master_prompt_zh", "natural": None},
    "mediation": {"probe": "probe_master_prompt_zh", "natural": None},
    "drafting": {"probe": "drafting_master_prompt_zh", "natural": None},
    "analysis": {"probe": "analysis_master_prompt_zh", "natural": "analysis_master_prompt_zh"},
}

TURN_RANGE = {  # archetype -> (min, max)
    "roleplay": (2, 4),
    "mediation": (2, 4),
    "drafting": (2, 4),
    "analysis": (1, 1),
}

NOTES_TAIL = "这不应是评分的唯一判别因素；请综合看整体表现。"

REQUIRED_FIELDS = {
    "id": str, "archetype": str, "domain": str, "title": str,
    "source": dict, "persona": dict, "turns": list,
    "format_instruction": dict, "scenario_notes": dict,
    "failure_mode": str, "red_flags": list, "tags": list,
}


def err_collector():
    errors = []

    def err(msg):
        errors.append(msg)
    return errors, err


def validate_record(rec, err):
    rid = rec.get("id", "<no-id>")
    for field, typ in REQUIRED_FIELDS.items():
        if field not in rec:
            err(f"{rid}: 缺字段 {field}")
        elif not isinstance(rec[field], typ):
            err(f"{rid}: 字段 {field} 类型应为 {typ.__name__}")
    if not re.fullmatch(r"EC-\d{2}", rec.get("id", "")):
        err(f"{rid}: id 格式应为 EC-NN")

    arch = rec.get("archetype")
    if arch not in ARCHETYPES:
        err(f"{rid}: archetype 非法: {arch}")
        return

    src = rec.get("source", {})
    if src.get("type") not in {"original", "adapted"}:
        err(f"{rid}: source.type 应为 original|adapted")
    if src.get("type") == "adapted" and "eqbench_id" not in src:
        err(f"{rid}: adapted 场景缺 source.eqbench_id")

    persona = rec.get("persona", {})
    for k in ("user_role", "context"):
        if not persona.get(k):
            err(f"{rid}: persona.{k} 缺失或为空")

    turns = rec.get("turns", [])
    lo, hi = TURN_RANGE[arch]
    if not (lo <= len(turns) <= hi):
        err(f"{rid}: {arch} 轮数应在 [{lo},{hi}]，实际 {len(turns)}")
    if turns and not turns[0].lstrip().startswith("["):
        err(f"{rid}: turns[0] 应以 [场景设定…] 方括号开头")
    for i, t in enumerate(turns):
        if not isinstance(t, str) or len(t.strip()) < 20:
            err(f"{rid}: turns[{i}] 过短或非字符串")

    fi = rec.get("format_instruction", {})
    expect = FORMAT_BY_ARCHETYPE[arch]
    if fi != expect:
        err(f"{rid}: format_instruction 应为 {expect}，实际 {fi}")
    for tmpl in {v for v in fi.values() if v}:
        if not (DATA / "candidate_prompts" / f"{tmpl}.txt").exists():
            err(f"{rid}: 模板文件不存在 candidate_prompts/{tmpl}.txt")

    notes = rec.get("scenario_notes", {})
    for mode in ("probe", "natural"):
        text = notes.get(mode, "")
        if not text or len(text) < 50:
            err(f"{rid}: scenario_notes.{mode} 缺失或过短")
        elif not text.rstrip().endswith(NOTES_TAIL):
            err(f"{rid}: scenario_notes.{mode} 未以规定句结尾")

    if not (2 <= len(rec.get("tags", [])) <= 4):
        err(f"{rid}: tags 应为 2-4 个")


def validate_criteria(err):
    """轻量交叉检查 rubric_criteria.yaml 与判官提示词的一致性（不依赖 yaml 库，按行解析 key）。"""
    crit_file = DATA / "rubric_criteria.yaml"
    if not crit_file.exists():
        err("缺 data/rubric_criteria.yaml")
        return
    text = crit_file.read_text(encoding="utf-8")

    def keys_in_section(section):
        m = re.search(rf"^{section}:\n(.*?)(?=^\S|\Z)", text, re.M | re.S)
        if not m:
            return []
        return re.findall(r"^\s*-\s*\{?key:\s*(\w+)", m.group(1), re.M)

    scored = keys_in_section("scored_criteria")
    probes = keys_in_section("probe_criteria")
    analysis = keys_in_section("analysis_criteria")
    if len(scored) != 9:
        err(f"scored_criteria 应 9 项，实际 {len(scored)}")
    if len(probes) != 12:
        err(f"probe_criteria 应 12 项，实际 {len(probes)}")
    if len(analysis) != 6:
        err(f"analysis_criteria 应 6 项，实际 {len(analysis)}")

    for prompt_name in ("rubric_probe_zh", "rubric_natural_zh"):
        p = DATA / "judge_prompts" / f"{prompt_name}.txt"
        if not p.exists():
            err(f"缺 judge_prompts/{prompt_name}.txt")
            continue
        ptext = p.read_text(encoding="utf-8")
        for k in scored + probes:
            if k not in ptext:
                err(f"{prompt_name}.txt 未引用标准 {k}")
    p = DATA / "judge_prompts" / "rubric_analysis_zh.txt"
    if p.exists():
        ptext = p.read_text(encoding="utf-8")
        for k in analysis:
            if k not in ptext:
                err(f"rubric_analysis_zh.txt 未引用标准 {k}")
    else:
        err("缺 judge_prompts/rubric_analysis_zh.txt")


LITE_FORMAT = {"roleplay": None, "mediation": None,
               "drafting": "drafting_master_prompt_zh", "analysis": "analysis_master_prompt_zh"}


def validate_lite():
    """校验 scenarios_lite.jsonl：47 条、单轮、lite 注释齐全带结尾句、与主数据集 id 对齐。"""
    errors, err = err_collector()
    path = DATA / "scenarios_lite.jsonl"
    if not path.exists():
        print(f"FAIL: 文件不存在 {path}")
        sys.exit(1)
    main_ids = {json.loads(l)["id"] for l in (DATA / "scenarios.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            err(f"第 {lineno} 行 JSON 解析失败: {e}")
    for r in records:
        rid = r.get("id", "<no-id>")
        for f in ("id", "archetype", "domain", "title", "prompt", "scenario_notes_lite",
                  "failure_mode", "red_flags", "tags"):
            if f not in r:
                err(f"{rid}: 缺字段 {f}")
        if not r.get("prompt", "").lstrip().startswith("["):
            err(f"{rid}: prompt 应以 [场景设定…] 方括号开头")
        notes = r.get("scenario_notes_lite", "")
        if not notes or len(notes) < 50:
            err(f"{rid}: scenario_notes_lite 缺失或过短")
        elif not notes.rstrip().endswith(NOTES_TAIL):
            err(f"{rid}: scenario_notes_lite 未以规定句结尾")
        if r.get("format_instruction") != LITE_FORMAT.get(r.get("archetype")):
            err(f"{rid}: format_instruction 应为 {LITE_FORMAT.get(r.get('archetype'))}")
    ids = {r.get("id") for r in records}
    if ids != main_ids:
        err(f"lite 与主数据集 id 不对齐: 差集 {sorted(ids ^ main_ids)}")
    print(f"lite 记录数: {len(records)}")
    if errors:
        print(f"\nFAIL ({len(errors)} 项):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("PASS: lite 全部检查通过")


def main():
    if "--lite" in sys.argv:
        validate_lite()
        return
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "scenarios.jsonl"
    errors, err = err_collector()

    if not path.exists():
        print(f"FAIL: 文件不存在 {path}")
        sys.exit(1)

    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            err(f"第 {lineno} 行 JSON 解析失败: {e}")

    for rec in records:
        validate_record(rec, err)

    ids = [r.get("id") for r in records]
    dupes = [i for i, c in Counter(ids).items() if c > 1]
    if dupes:
        err(f"id 重复: {dupes}")

    dom_counts = Counter(r.get("domain") for r in records)
    for dom, (n, allowed) in QUOTA.items():
        if dom_counts.get(dom, 0) != n:
            err(f"domain '{dom}' 应 {n} 条，实际 {dom_counts.get(dom, 0)}")
        for r in records:
            if r.get("domain") == dom and r.get("archetype") not in allowed:
                err(f"{r.get('id')}: domain '{dom}' 不允许原型 {r.get('archetype')}")
    for dom in dom_counts:
        if dom not in QUOTA:
            err(f"未知 domain: {dom}")

    validate_criteria(err)

    # 统计报告
    arch_counts = Counter(r.get("archetype") for r in records)
    src_counts = Counter(r.get("source", {}).get("type") for r in records)
    print(f"记录数: {len(records)}")
    print(f"原型分布: {dict(arch_counts)}")
    print(f"来源分布: {dict(src_counts)}")
    print(f"子领域: {dict(dom_counts)}")
    red_flag_n = sum(1 for r in records if r.get("red_flags"))
    print(f"含红旗场景: {red_flag_n}")

    if errors:
        print(f"\nFAIL ({len(errors)} 项):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("\nPASS: 全部检查通过")


if __name__ == "__main__":
    main()
