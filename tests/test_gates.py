#!/usr/bin/env python3
"""
test_gates.py — 统一闸门闭环测试（THESIS 推论 3）

验证单一闸门模型：
  auto_pass → 批准；auto_reject → 打回；escalate → dev/test/pm 三级人工依次裁决。

运行: python3 -m unittest tests.test_gates -v  （或 discover 全量）
"""
import importlib
import json
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_contract as vc

PASS_OUTPUT = {
    "task_id": "task-gate-001",
    "status": "done",
    "commits": ["abc123"],
    "evidence": {
        "test_result": "pass",
        "diff_stat": "1 file changed, 49 insertions(+)",
        "files_changed": ["backend/app/health.py"],
    },
}


class TestGatesLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DEV_FLOW_HOME"] = self.tmp
        # 模块导入时读取环境变量，按依赖序重载
        importlib.reload(vc)
        import scorecard
        self.scorecard = importlib.reload(scorecard)
        import gates
        self.gates = importlib.reload(gates)

    def tearDown(self):
        os.environ.pop("DEV_FLOW_HOME", None)

    def _make_task(self, output_doc, task_id="task-gate-001"):
        task_dir = os.path.join(self.tmp, ".hermes", "tasks", task_id)
        os.makedirs(task_dir, exist_ok=True)
        with open(os.path.join(task_dir, "output.json"), "w") as f:
            json.dump(output_doc, f)
        with open(os.path.join(task_dir, "state.json"), "w") as f:
            json.dump({"task_id": task_id, "status": "VERIFY_GATE",
                       "evidence": {}, "gate_history": []}, f)
        return task_id

    # ── 自动支路 ──

    def test_auto_pass_approved(self):
        """测试 green + 产出可核查 → 自动批准，gate_history 留痕。"""
        tid = self._make_task(PASS_OUTPUT)
        d = self.gates.decide(tid)
        self.assertEqual(d["decision"], "approved")
        self.assertEqual(d["by"], "auto")
        self.assertEqual(d["next"], "dev-integrate")
        state = self.gates.load_state(tid)
        self.assertEqual(state["gate_history"][0]["verdict"], "auto_pass")

    def test_auto_reject_on_test_fail(self):
        """测试失败 → 自动打回，反馈含原因，next 回 EXECUTING。"""
        bad = {**PASS_OUTPUT, "evidence": {**PASS_OUTPUT["evidence"], "test_result": "fail"}}
        tid = self._make_task(bad)
        d = self.gates.decide(tid)
        self.assertEqual(d["decision"], "rejected")
        self.assertEqual(d["next"], "EXECUTING")
        self.assertIn("测试失败", d["feedback"])

    def test_contract_violation_rejected(self):
        """契约违反 → 打回（闸门 0 经统一闸门生效）。"""
        tid = self._make_task({"status": "done"})  # 缺 task_id
        d = self.gates.decide(tid)
        self.assertEqual(d["decision"], "rejected")

    # ── 人工支路 ──

    def _escalated_task(self):
        doc = {**PASS_OUTPUT, "evidence": {**PASS_OUTPUT["evidence"], "test_result": "skipped"}}
        tid = self._make_task(doc)
        d = self.gates.decide(tid)
        assert d["decision"] == "escalated", d
        return tid

    def test_escalate_enters_human_chain(self):
        """证据不充分 → 进入三级人工角色，首个待裁决为 dev。"""
        tid = self._escalated_task()
        st = self.gates.status(tid)
        self.assertEqual(st["pending_role"], "dev")
        self.assertEqual(st["human_gates"]["required"], ["dev", "test", "pm"])

    def test_human_full_chain_approved(self):
        """dev → test → pm 依次 approve → 批准，记录完整审批链。"""
        tid = self._escalated_task()
        self.assertEqual(self.gates.human(tid, "dev", "approve")["next"], "human:test")
        self.assertEqual(self.gates.human(tid, "test", "approve")["next"], "human:pm")
        d = self.gates.human(tid, "pm", "approve")
        self.assertEqual(d["decision"], "approved")
        self.assertEqual(d["approved_by"], ["dev", "test", "pm"])
        self.assertEqual(d["next"], "dev-integrate")

    def test_human_out_of_order_rejected(self):
        """顺序错误：pm 不能越过 dev/test 先裁决。"""
        tid = self._escalated_task()
        r = self.gates.human(tid, "pm", "approve")
        self.assertIn("顺序错误", r["error"])

    def test_human_reject_stops_chain(self):
        """任一角色打回 → 链路终止，反馈回 EXECUTING。"""
        tid = self._escalated_task()
        self.gates.human(tid, "dev", "approve")
        d = self.gates.human(tid, "test", "reject", "测试产物不可信")
        self.assertEqual(d["decision"], "rejected")
        self.assertEqual(d["feedback"], "测试产物不可信")
        st = self.gates.status(tid)
        self.assertIsNone(st["pending_role"])
        # 打回后不允许继续裁决
        r = self.gates.human(tid, "pm", "approve")
        self.assertIn("error", r)

    def test_human_without_decide_errors(self):
        """未跑 decide 直接人工裁决 → 报错。"""
        tid = self._make_task(PASS_OUTPUT)
        r = self.gates.human(tid, "dev", "approve")
        self.assertIn("error", r)

    def test_gate_history_records_human_actions(self):
        """每次人工裁决都进 gate_history（推论 3：人的介入被记录）。"""
        tid = self._escalated_task()
        self.gates.human(tid, "dev", "approve", "diff 已核")
        self.gates.human(tid, "test", "approve")
        self.gates.human(tid, "pm", "approve")
        state = self.gates.load_state(tid)
        kinds = [h["kind"] for h in state["gate_history"]]
        self.assertEqual(kinds, ["auto", "human", "human", "human"])

    # ── approval_state（闭环收口，integrate 依赖） ──

    def test_approval_state_after_human_chain(self):
        """人工链批准后，approval_state 必须稳定返回 approved——
        回归：integrate_hooks 不得重跑 decide 把已批准的人工链重置回 escalated。"""
        tid = self._escalated_task()
        self.gates.human(tid, "dev", "approve")
        self.gates.human(tid, "test", "approve")
        self.gates.human(tid, "pm", "approve")
        a = self.gates.approval_state(tid)
        self.assertEqual(a["decision"], "approved")
        self.assertEqual(a["by"], "human:all")
        # 再次查询不得改变结论（幂等只读）
        a2 = self.gates.approval_state(tid)
        self.assertEqual(a2["decision"], "approved")

    def test_approval_state_auto_paths(self):
        """自动支路：auto_pass → approved；auto_reject → rejected。"""
        tid = self._make_task(PASS_OUTPUT, "task-gate-auto")
        self.gates.decide(tid)
        self.assertEqual(self.gates.approval_state(tid)["decision"], "approved")

        bad = {**PASS_OUTPUT, "evidence": {**PASS_OUTPUT["evidence"], "test_result": "fail"}}
        tid2 = self._make_task(bad, "task-gate-auto2")
        self.gates.decide(tid2)
        a = self.gates.approval_state(tid2)
        self.assertEqual(a["decision"], "rejected")
        self.assertEqual(a["by"], "auto")

    def test_approval_state_pending_when_fresh(self):
        """从未裁决的任务 → pending，by 为 None（触发 integrate 补跑 decide 的分支）。"""
        tid = self._make_task(PASS_OUTPUT)
        a = self.gates.approval_state(tid)
        self.assertEqual(a["decision"], "pending")
        self.assertIsNone(a["by"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
