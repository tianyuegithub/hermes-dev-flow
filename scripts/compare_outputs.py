#!/usr/bin/env python3
"""
compare_outputs.py — 多 CLI 择优对比引擎

用法:
  python3 compare_outputs.py <output-a.json> <output-b.json>
  python3 compare_outputs.py <task_id>  (对比 task 下的 output-claude.json 和 output-codex.json)

输出:
  JSON { winner, score_a, score_b, recommendation, reason }
"""
import json, os, sys


def compare(output_a: dict, output_b: dict, name_a: str = "A", name_b: str = "B") -> dict:
    """对比两个 output，返回推荐"""
    score_a = 0
    score_b = 0
    reasons = []

    # ── 1. 是否有 commit（权重最高） ──
    commits_a = output_a.get("commits", [])
    commits_b = output_b.get("commits", [])

    if commits_a and not commits_b:
        score_a += 50
        reasons.append(f"{name_a} 有 commit({len(commits_a)}个)，{name_b} 无")
    elif commits_b and not commits_a:
        score_b += 50
        reasons.append(f"{name_b} 有 commit({len(commits_b)}个)，{name_a} 无")
    elif commits_a and commits_b:
        score_a += 30
        score_b += 30
        reasons.append(f"双方都有 commit")

    # ── 2. diff 行数（完整度，但不能过大说明偏离需求） ──
    diff_a = output_a.get("evidence", {}).get("diff_stat", "")
    diff_b = output_b.get("evidence", {}).get("diff_stat", "")

    lines_a = _extract_changes(diff_a)
    lines_b = _extract_changes(diff_b)

    if lines_a > 0 and lines_b > 0:
        # 都不超过 200 行说明在合理范围
        if 10 <= lines_a <= 200:
            score_a += 20
        if 10 <= lines_b <= 200:
            score_b += 20
        reasons.append(f"diff: {name_a}={lines_a}行, {name_b}={lines_b}行")
    elif lines_a > 0:
        score_a += 20
        reasons.append(f"{name_a} 有 diff({lines_a}行)，{name_b} 无")
    elif lines_b > 0:
        score_b += 20
        reasons.append(f"{name_b} 有 diff({lines_b}行)，{name_a} 无")

    # ── 3. 成本 ──
    cost_a = output_a.get("evidence", {}).get("claude_cost", 0) or 0
    cost_b = output_b.get("evidence", {}).get("claude_cost", 0) or 0

    if cost_a > 0 and cost_b > 0:
        # 成本更低的加 5 分
        if cost_a < cost_b:
            score_a += 5
            reasons.append(f"{name_a} 成本更低(\${cost_a:.03f} vs \${cost_b:.03f})")
        else:
            score_b += 5
            reasons.append(f"{name_b} 成本更低(\${cost_b:.03f} vs \${cost_a:.03f})")

    # ── 4. turns（效率） ──
    turns_a = output_a.get("evidence", {}).get("claude_turns", 0) or 0
    turns_b = output_b.get("evidence", {}).get("claude_turns", 0) or 0

    if turns_a > 0 and turns_b > 0:
        if turns_a < turns_b:
            score_a += 3
            reasons.append(f"{name_a} turns 更少({turns_a} vs {turns_b})")
        else:
            score_b += 3
            reasons.append(f"{name_b} turns 更少({turns_b} vs {turns_a})")

    # ── 5. self_check（额外加分） ──
    sc_a = output_a.get("evidence", {}).get("self_check", [])
    sc_b = output_b.get("evidence", {}).get("self_check", [])
    if isinstance(sc_a, list) and all(isinstance(s, dict) and s.get("met") for s in sc_a if isinstance(s, dict)):
        score_a += 10
        reasons.append(f"{name_a} self_check 全部通过")
    if isinstance(sc_b, list) and all(isinstance(s, dict) and s.get("met") for s in sc_b if isinstance(s, dict)):
        score_b += 10
        reasons.append(f"{name_b} self_check 全部通过")

    # ── 裁决 ──
    if score_a == score_b == 0:
        winner = None
        recommendation = "两者都没有产出，建议 escalation"
    elif score_a > score_b:
        winner = name_a
        recommendation = f"推荐 {name_a} (得分 {score_a} vs {score_b})"
    elif score_b > score_a:
        winner = name_b
        recommendation = f"推荐 {name_b} (得分 {score_b} vs {score_a})"
    else:
        winner = "either"
        recommendation = f"双方得分相同({score_a})，建议人工选择"

    return {
        "winner": winner,
        "score_a": score_a,
        "score_b": score_b,
        "name_a": name_a,
        "name_b": name_b,
        "recommendation": recommendation,
        "reasons": reasons,
    }


def _extract_changes(diff_stat: str) -> int:
    """从 diff stat 提取变更行数: '1 file changed, 27 insertions(+), 27 deletions(-)' → 54"""
    import re
    total = 0
    inserts = re.search(r"(\d+) insertion", diff_stat.replace("(+)", ""))
    deletes = re.search(r"(\d+) deletion", diff_stat.replace("(-)", ""))
    if inserts:
        total += int(inserts.group(1))
    if deletes:
        total += int(deletes.group(1))
    return total


if __name__ == "__main__":
    if len(sys.argv) == 2:
        # task_id 模式: 读 tasks/<id>/output-claude.json + output-codex.json
        task_id = sys.argv[1]
        task_dir = os.path.expanduser(f"~/Codes/ai-dev-flow/.hermes/tasks/{task_id}")

        with open(os.path.join(task_dir, "output-claude.json")) as f:
            a = json.load(f)
        with open(os.path.join(task_dir, "output-codex.json")) as f:
            b = json.load(f)

        result = compare(a, b, "Claude", "Codex")
    elif len(sys.argv) == 3:
        with open(sys.argv[1]) as f:
            a = json.load(f)
        with open(sys.argv[2]) as f:
            b = json.load(f)
        result = compare(a, b, os.path.basename(sys.argv[1]), os.path.basename(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))
