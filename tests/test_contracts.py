#!/usr/bin/env python3
"""
test_contracts.py — 契约强制校验测试套件（conformance）

对应 docs/THESIS.md 推论 1：契约必须可执行，否则不存在。
每个用例都是"契约可强制"这一宣称的可运行证据。

运行: python3 -m pytest tests/test_contracts.py -v
      或 python3 tests/test_contracts.py
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import validate_contract as vc


# ── 合法样本 ──────────────────────────────────────────────────

VALID_INPUT = {
    "task_id": "task-20260730-001",
    "task_type": "feature",
    "repo_url": "ssh://git@example.com/user/repo.git",
    "goal": "加一个 /health 接口",
    "acceptance": ["/health 返回 200"],
}

VALID_OUTPUT = {
    "task_id": "task-20260730-001",
    "status": "done",
    "branch": "dev-flow/task-20260730-001",
    "commits": ["abc123"],
    "evidence": {
        "test_result": "pass",
        "diff_stat": "1 file changed, 49 insertions(+)",
        "files_changed": ["backend/app/health.py"],
    },
    "self_check": [
        {"criterion": "/health 返回 200", "met": True, "proof": "curl 输出 200 ok"}
    ],
}

VALID_ESCALATE = {
    "task_id": "task-20260730-001",
    "type": "escalate",
    "question": "是否删除旧表？",
    "options": [
        {"id": "a", "desc": "直接删除"},
        {"id": "b", "desc": "先备份再删"},
    ],
    "recommendation": "b",
}


def load_schema(name):
    with open(os.path.join(vc.CONTRACTS_DIR, vc.CONTRACT_NAMES[name])) as f:
        return json.load(f)


class TestInputContract(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema("input")

    def test_valid_minimal(self):
        self.assertEqual(vc.validate(VALID_INPUT, self.schema), [])

    def test_missing_required(self):
        bad = {k: v for k, v in VALID_INPUT.items() if k != "goal"}
        errors = vc.validate(bad, self.schema)
        self.assertTrue(any("goal" in e for e in errors))

    def test_task_type_enum_accepts_routing_table_types(self):
        """路由表里的 test/dependency 类型必须被契约接受（2026-07-30 一致性修复）。"""
        for t in ("test", "dependency", "refactor", "research"):
            doc = {**VALID_INPUT, "task_type": t}
            self.assertEqual(vc.validate(doc, self.schema), [], f"task_type={t} 应合法")

    def test_task_type_enum_rejects_unknown(self):
        doc = {**VALID_INPUT, "task_type": "whatever"}
        self.assertTrue(vc.validate(doc, self.schema))

    def test_worker_enum_accepts_opencode(self):
        doc = {**VALID_INPUT, "worker": "opencode"}
        self.assertEqual(vc.validate(doc, self.schema), [])

    def test_worker_enum_rejects_unknown(self):
        doc = {**VALID_INPUT, "worker": "gpt-cli"}
        self.assertTrue(vc.validate(doc, self.schema))


class TestOutputContract(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema("output")

    def test_valid_full(self):
        self.assertEqual(vc.validate(VALID_OUTPUT, self.schema), [])

    def test_valid_minimal(self):
        self.assertEqual(vc.validate({"task_id": "t1", "status": "blocked"}, self.schema), [])

    def test_missing_task_id(self):
        bad = {k: v for k, v in VALID_OUTPUT.items() if k != "task_id"}
        self.assertTrue(any("task_id" in e for e in vc.validate(bad, self.schema)))

    def test_status_enum(self):
        bad = {**VALID_OUTPUT, "status": "finished"}  # 不是 done/blocked/escalate
        self.assertTrue(vc.validate(bad, self.schema))

    def test_self_check_item_missing_proof(self):
        bad = {**VALID_OUTPUT, "self_check": [{"criterion": "x", "met": True}]}
        errors = vc.validate(bad, self.schema)
        self.assertTrue(any("proof" in e and "self_check[0]" in e for e in errors))

    def test_test_result_enum(self):
        bad = {**VALID_OUTPUT, "evidence": {"test_result": "maybe"}}
        self.assertTrue(vc.validate(bad, self.schema))

    def test_wrong_type(self):
        bad = {**VALID_OUTPUT, "commits": "abc123"}  # 应为数组
        self.assertTrue(any("commits" in e for e in vc.validate(bad, self.schema)))


class TestEscalateContract(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema("escalate")

    def test_valid(self):
        self.assertEqual(vc.validate(VALID_ESCALATE, self.schema), [])

    def test_type_const(self):
        bad = {**VALID_ESCALATE, "type": "question"}
        self.assertTrue(vc.validate(bad, self.schema))

    def test_options_min_items(self):
        bad = {**VALID_ESCALATE, "options": [{"id": "a", "desc": "唯一选项"}]}
        errors = vc.validate(bad, self.schema)
        self.assertTrue(any("至少 2 项" in e for e in errors))

    def test_options_max_items(self):
        bad = {**VALID_ESCALATE,
               "options": [{"id": str(i), "desc": f"选项{i}"} for i in range(5)]}
        self.assertTrue(any("至多 4 项" in e for e in vc.validate(bad, self.schema)))

    def test_option_missing_desc(self):
        bad = {**VALID_ESCALATE, "options": [{"id": "a"}, {"id": "b", "desc": "x"}]}
        self.assertTrue(any("desc" in e for e in vc.validate(bad, self.schema)))


class TestScorecardContractGate(unittest.TestCase):
    """契约一票否决：违反契约 → auto_reject，任何分数不可赦免。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["DEV_FLOW_HOME"] = self.tmp
        # TASKS_DIR / HOME 在模块导入时读取环境变量，需按依赖序重载
        importlib.reload(vc)
        import scorecard
        self.scorecard = importlib.reload(scorecard)

    def tearDown(self):
        os.environ.pop("DEV_FLOW_HOME", None)

    def _make_task(self, output_doc):
        task_id = "task-test-001"
        task_dir = os.path.join(self.tmp, ".hermes", "tasks", task_id)
        os.makedirs(task_dir)
        with open(os.path.join(task_dir, "output.json"), "w") as f:
            json.dump(output_doc, f)
        with open(os.path.join(task_dir, "state.json"), "w") as f:
            json.dump({"evidence": {}}, f)
        return task_id

    def test_invalid_output_auto_reject_despite_commits(self):
        """有 commit 但 output 违反契约 → 仍打回（50 分不可赦免）。"""
        bad = {"status": "done", "commits": ["abc"]}  # 缺 task_id
        task_id = self._make_task(bad)
        result = self.scorecard.evaluate(task_id, auto=True)
        self.assertEqual(result["verdict"], "auto_reject")
        self.assertEqual(result["action"], "REJECT")
        self.assertIn("契约违反", result["recommendation"])
        self.assertFalse(result["contract"]["valid"])

    def test_valid_output_with_evidence_auto_pass(self):
        """契约合规 + 测试 pass + 有 commit + diff 在合理区间 → auto_pass。"""
        task_id = self._make_task(VALID_OUTPUT)
        result = self.scorecard.evaluate(task_id, auto=True)
        self.assertEqual(result["verdict"], "auto_pass")
        self.assertTrue(result["contract"]["valid"])

    def test_test_fail_auto_reject(self):
        """外部证据为负（test_result=fail）→ 一票否决 auto_reject，有 commit 也不可赦。"""
        bad = {**VALID_OUTPUT, "evidence": {**VALID_OUTPUT["evidence"], "test_result": "fail"}}
        task_id = self._make_task(bad)
        result = self.scorecard.evaluate(task_id, auto=True)
        self.assertEqual(result["verdict"], "auto_reject")
        self.assertIn("测试失败", result["recommendation"])

    def test_test_skipped_escalate_not_pass(self):
        """测试 skipped → 证据不充分，必须 escalate 给人，禁止 auto_pass。"""
        doc = {**VALID_OUTPUT, "evidence": {**VALID_OUTPUT["evidence"], "test_result": "skipped"}}
        task_id = self._make_task(doc)
        result = self.scorecard.evaluate(task_id, auto=True)
        self.assertEqual(result["verdict"], "escalate")
        self.assertEqual(result["action"], "ESCALATE")

    def test_worker_blocked_never_auto_pass(self):
        """worker 自声明 blocked/escalate → 禁止 auto_pass，交人裁决。"""
        doc = {**VALID_OUTPUT, "status": "blocked"}
        task_id = self._make_task(doc)
        result = self.scorecard.evaluate(task_id, auto=True)
        self.assertEqual(result["verdict"], "escalate")

    def test_self_check_scores_zero(self):
        """推论 2：agent 自报的 self_check 全部 met 也不得分——无外部证据 → auto_reject。"""
        doc = {
            "task_id": "task-test-001",
            "status": "done",
            "self_check": [
                {"criterion": "功能正常", "met": True, "proof": "我试过了"},
                {"criterion": "没有回归", "met": True, "proof": "应该没有"},
            ],
        }
        task_id = self._make_task(doc)
        result = self.scorecard.evaluate(task_id, auto=True)
        self.assertEqual(result["verdict"], "auto_reject")
        self.assertNotIn("self_check", result["scores"])
        # 自报数据仍被展示，但明确标注为参考
        self.assertIn("参考", result["reference"]["note"])


class TestCLI(unittest.TestCase):
    def _write_tmp(self, doc):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f)
        return path

    def test_cli_valid_exit_0(self):
        path = self._write_tmp(VALID_OUTPUT)
        r = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "validate_contract.py"), "output", path],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(json.loads(r.stdout)["valid"])

    def test_cli_invalid_exit_1(self):
        path = self._write_tmp({"status": "done"})
        r = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "validate_contract.py"), "output", path],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(json.loads(r.stdout)["valid"])

    def test_cli_missing_file_exit_2(self):
        r = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "validate_contract.py"), "output", "/nonexistent/x.json"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
