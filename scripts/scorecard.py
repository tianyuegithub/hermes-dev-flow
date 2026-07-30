#!/usr/bin/env python3
"""
scorecard.py — 自动评分（契约问责制，2026-07-30 重构）

评分哲学（docs/THESIS.md 三条推论）:
  1. 契约必须可执行  → 闸门 0: output.json 违反契约 = auto_reject，无分可赦
  2. 证据必须来自外部 → 只给外部可核查信号计分；agent 自报 (self_check) 零分，
                        仅作参考展示，永远不影响裁决
  3. 人是裁决者       → 证据齐全才 auto_pass；证据不足 escalate 给人；
                        外部证据为负（测试失败）或 worker 声明 blocked/escalate
                        时，禁止 auto_pass

评分维度（满分 100，全部来自 evidence / 外部信号）:
  ✅ test_result=pass   → 30 分  (测试产物，闸门可去工作副本复核)
  ✅ 有 commit          → 25 分  (git log 可核查)
  ✅ diff 完整度         → 15 分  (10-200 行正常区间，git diff 可核查)
  ✅ files_changed 列表  → 10 分  (与 diff 交叉核对)
  ✅ delta_verify 匹配   → 12 分  (对照 OpenSpec delta 规范)
  ○ 成本/turns 效率      → 5+3 分 (参考分，只影响同档排序)

否决项（先于评分）:
  ✗ 契约违反            → auto_reject (contract_violation)
  ✗ test_result=fail    → auto_reject (test_failed)
  ✗ status=blocked/escalate → escalate (worker 自声明无法自决，交人裁决)

阈值:
  >= 75  → auto_pass   (测试 green + 产出可核查 + diff 合理)
  40-75  → escalate    (证据不充分 — 典型: 测试 skipped / 无测试)
  < 40   → auto_reject (无产出或无任何可核查证据)

用法: python3 scorecard.py <task_id> [--auto]
      --auto: 自动决策，不等待人拍板
"""
import os, sys, json, subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_contract import validate_task_artifact
import paths

HOME = paths.home()

THRESHOLDS = {"auto_pass": 75, "escalate": 40}


def load_evidence(task_id: str) -> dict:
    """加载任务的 evidence + output"""
    task_dir = os.path.join(HOME, ".hermes", "tasks", task_id)
    evidence = {}
    try:
        with open(os.path.join(task_dir, "state.json")) as f:
            d = json.load(f)
            evidence.update(d.get("evidence", {}))
    except: pass
    try:
        with open(os.path.join(task_dir, "output.json")) as f:
            d = json.load(f)
            evidence["commits"] = d.get("commits", [])
            evidence["status"] = d.get("status", "?")
            # output.json 里的 evidence 优先级更高（契约产物，经闸门 0 校验）
            evidence.update({k: v for k, v in d.get("evidence", {}).items() if v})
    except: pass
    return evidence


# ── 外部证据计分 ─────────────────────────────────────────────

def score_test_result(evidence: dict) -> float:
    """测试信号: pass=30。fail 不走这里（是否决项）。skipped/缺失=0，中立。"""
    return 30.0 if evidence.get("test_result") == "pass" else 0.0


def score_commit(evidence: dict) -> float:
    """有 commit = 25 分（git log 可核查）"""
    return 25.0 if evidence.get("commits") else 0.0


def score_diff(evidence: dict) -> float:
    """diff 完整度: 10-200 行 = 15 分，太少/太多递减"""
    diff = evidence.get("diff_stat", "")
    if not diff:
        return 0.0
    import re
    lines = 0
    for m in re.finditer(r"(\d+) insertion|(\d+) deletion", diff):
        lines += int(m.group(1) or 0) + int(m.group(2) or 0)
    files = diff.count("file changed")
    if not files and not lines:
        return 4.0  # 有 diff 但解析不了
    if 10 <= lines <= 200:
        return 15.0
    elif lines < 10:
        return 7.0
    else:
        return max(4.0, 15.0 - (lines - 200) * 0.04)


def score_files_changed(evidence: dict) -> float:
    """files_changed 列表非空 = 10 分（与 diff_stat 交叉核对用）"""
    return 10.0 if evidence.get("files_changed") else 0.0


def score_delta_verify(task_id: str) -> float:
    """Delta verify 匹配度（调用 delta_verify.py，最高 12 分）"""
    try:
        result = subprocess.run(
            [sys.executable, paths.script("delta_verify.py"), task_id],
            capture_output=True, text=True, timeout=10
        )
        d = json.loads(result.stdout)
        status = d.get("status", "skipped")
        if status == "skipped":
            return 0.0
        matched = d.get("matched", 0)
        total = matched + d.get("missing", 0) + d.get("extra", 0)
        if total == 0:
            return 0.0
        return max(0, (matched / total) * 12)
    except:
        return 0.0


# ── 参考分（效率，只影响同档排序，救不了证据缺失） ────────────

def score_cost(evidence: dict) -> float:
    cost = evidence.get("claude_cost", 99)
    if cost <= 0.03: return 5.0
    elif cost <= 0.10: return 4.0
    elif cost <= 0.50: return 2.0
    return 0.0


def score_turns(evidence: dict) -> float:
    turns = evidence.get("claude_turns", 99)
    if turns <= 5: return 3.0
    elif turns <= 15: return 2.0
    elif turns <= 30: return 1.0
    return 0.0


# ── 裁决 ─────────────────────────────────────────────────────

def _verdict(total: float) -> tuple:
    if total >= THRESHOLDS["auto_pass"]:
        return "auto_pass", "自动通过 — 测试 green 且产出可核查，无需人工介入"
    if total >= THRESHOLDS["escalate"]:
        return "escalate", "证据不充分（常见于测试未运行）— 携带证据推送给人裁决"
    return "auto_reject", "自动打回 — 无产出或无可核查证据"


def evaluate(task_id: str, auto: bool = False) -> dict:
    """综合评分。否决项先于评分；自报数据永不计分。"""
    base = {
        "task_id": task_id,
        "max_possible": 100,
        "thresholds": THRESHOLDS,
        "auto": auto,
        "evaluated_at": datetime.now().isoformat(),
    }

    def finalize(verdict, recommendation, **extra):
        result = {**base, "verdict": verdict, "recommendation": recommendation, **extra}
        if auto:
            result["action"] = {"auto_pass": "PASS", "auto_reject": "REJECT",
                                "escalate": "ESCALATE"}[verdict]
        return result

    # ── 闸门 0：契约强制校验（推论 1） ──
    contract_valid, _, contract_result = validate_task_artifact(task_id, "output")
    if contract_valid is False:
        return finalize(
            "auto_reject",
            "契约违反 — output.json 不符合 output 契约，直接打回，worker 须修正契约产物后重交",
            total=0.0, contract=contract_result, scores={},
        )

    evidence = load_evidence(task_id)

    # ── 否决项 1：外部证据为负 — 测试失败（推论 2） ──
    if evidence.get("test_result") == "fail":
        return finalize(
            "auto_reject",
            "测试失败 — 外部证据为负，直接打回。修复后重交，附新的测试产物",
            total=0.0, contract=contract_result, scores={},
        )

    # ── 否决项 2：worker 自声明无法自决 — 禁止 auto_pass（推论 3） ──
    if evidence.get("status") in ("blocked", "escalate"):
        return finalize(
            "escalate",
            f"worker 声明 {evidence['status']} — 无法自决，交人裁决",
            total=None, contract=contract_result, scores={},
        )

    # ── 计分（全部外部证据 + 少量参考分） ──
    scores = {
        "test_pass": score_test_result(evidence),
        "commit": score_commit(evidence),
        "diff_completeness": score_diff(evidence),
        "files_changed": score_files_changed(evidence),
        "delta_verify": score_delta_verify(task_id),
        "cost_efficiency": score_cost(evidence),
        "turn_efficiency": score_turns(evidence),
    }
    total = sum(scores.values())
    verdict, recommendation = _verdict(total)

    return finalize(
        verdict, recommendation,
        total=round(total, 1),
        contract=contract_result,
        scores=scores,
        reference={
            "note": "以下为 agent 自报数据，仅作参考，不影响裁决（THESIS 推论 2）",
            "self_check": evidence.get("self_check", []),
        },
    )


if __name__ == "__main__":
    task_id = sys.argv[1]
    auto = "--auto" in sys.argv
    result = evaluate(task_id, auto)
    print(json.dumps(result, indent=2, ensure_ascii=False))
