#!/usr/bin/env python3
"""
scorecard.py — 自动评分替代人工闸门（Paseo/HomeRail 模式）

评分维度（权重递减）:
  ✅ 有 commit          → 50 分 (有产出 > 无产出)
  ✅ diff 完整度         → 20 分 (10-200 行正常范围)
  ✅ self_check 通过    → 10 分 (全部验收条件 met)
  ✅ 成本更低            → 5 分 (对比同级任务历史)
  ✅ turns 更少          → 3 分 (效率参考)
  ✅ delta_verify 匹配   → 12 分 (对照 OpenSpec delta 规范)

阈值:
  >= 70  → auto_pass   (自动通过，不阻塞)
  50-70  → escalate    (推送给用户决策)
  < 50   → auto_reject (自动打回)

用法: python3 scorecard.py <task_id> [--auto]
      --auto: 自动决策，不等待人拍板
"""
import os, sys, json, subprocess
from datetime import datetime


def load_evidence(task_id: str) -> dict:
    """加载任务的 evidence + output"""
    task_dir = os.path.expanduser(f"~/Codes/ai-dev-flow/.hermes/tasks/{task_id}")
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
    except: pass
    return evidence


def score_commit(evidence: dict) -> float:
    """有 commit = 50 分"""
    commits = evidence.get("commits", [])
    # 远程 diff (如果没有本地 commit，从 git 取)
    diff = evidence.get("diff_stat", "")
    return 50.0 if (commits or diff) else 0.0


def score_diff(evidence: dict) -> float:
    """diff 完整度: 10-200 行加 20 分，太少/太多递减"""
    diff = evidence.get("diff_stat", "")
    if not diff:
        return 0.0
    # 提取行数: "1 file changed, 49 insertions(+)" 或 "2 files changed, 5 insertions(+), 3 deletions(-)"
    import re
    lines = 0
    for m in re.finditer(r"(\d+) insertion|(\d+) deletion", diff):
        lines += int(m.group(1) or 0) + int(m.group(2) or 0)
    files = diff.count("file changed")
    if not files and not lines:
        return 5.0  # 有 diff 但解析不了
    if 10 <= lines <= 200:
        return 20.0
    elif lines < 10:
        return 10.0  # 太少
    else:
        return max(5.0, 20.0 - (lines - 200) * 0.05)  # 太多递减，最低 5


def score_cost(evidence: dict) -> float:
    """成本: 越低越好，$0.10 以下满分"""
    cost = evidence.get("claude_cost", 99)
    if cost <= 0.03:
        return 5.0
    elif cost <= 0.10:
        return 4.0
    elif cost <= 0.50:
        return 2.0
    else:
        return 0.0


def score_turns(evidence: dict) -> float:
    """turns: 越少越好，5以下满分"""
    turns = evidence.get("claude_turns", 99)
    if turns <= 5:
        return 3.0
    elif turns <= 15:
        return 2.0
    elif turns <= 30:
        return 1.0
    else:
        return 0.0


def score_self_check(evidence: dict) -> float:
    """self_check: 全部 met 加分"""
    if evidence.get("self_check_all_met"):
        return 10.0
    return 0.0


def score_delta_verify(task_id: str) -> float:
    """Delta verify 匹配度（调用 delta_verify.py）"""
    try:
        result = subprocess.run(
            [sys.executable,
             os.path.expanduser("~/Codes/ai-dev-flow/scripts/delta_verify.py"),
             task_id],
            capture_output=True, text=True, timeout=10
        )
        d = json.loads(result.stdout)
        status = d.get("status", "skipped")
        if status == "skipped":
            return 0.0  # 无 delta specs
        matched = d.get("matched", 0)
        total = matched + d.get("missing", 0) + d.get("extra", 0)
        if total == 0:
            return 0.0
        return max(0, (matched / total) * 12)  # 最高 12 分
    except:
        return 0.0


def evaluate(task_id: str, auto: bool = False) -> dict:
    """综合评分"""
    evidence = load_evidence(task_id)

    scores = {
        "commit": score_commit(evidence),
        "diff_completeness": score_diff(evidence),
        "self_check": score_self_check(evidence),
        "cost_efficiency": score_cost(evidence),
        "turn_efficiency": score_turns(evidence),
        "delta_verify": score_delta_verify(task_id),
    }

    total = sum(scores.values())

    if total >= 70:
        verdict = "auto_pass"
        recommendation = "自动通过 — 无需人工介入"
    elif total >= 50:
        verdict = "escalate"
        recommendation = "证据不充分 — 推送给用户决策"
    else:
        verdict = "auto_reject"
        recommendation = "自动打回 — 无产出或严重不达标"

    result = {
        "task_id": task_id,
        "total": round(total, 1),
        "max_possible": 100,
        "verdict": verdict,
        "recommendation": recommendation,
        "scores": scores,
        "thresholds": {"auto_pass": 70, "escalate": 50},
        "auto": auto,
        "evaluated_at": datetime.now().isoformat(),
    }

    if auto and verdict == "auto_pass":
        result["action"] = "PASS"
    elif auto and verdict == "auto_reject":
        result["action"] = "REJECT"
    elif auto and verdict == "escalate":
        result["action"] = "ESCALATE"

    return result


if __name__ == "__main__":
    task_id = sys.argv[1]
    auto = "--auto" in sys.argv
    result = evaluate(task_id, auto)
    print(json.dumps(result, indent=2, ensure_ascii=False))
