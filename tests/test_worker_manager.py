#!/usr/bin/env python3
"""
test_worker_manager.py — Manager 调度器单测（临时 Pod 唯一模式）

覆盖:
  - parse_blpop: redis-cli raw/交互两种输出格式
  - build_pod_spec: 安全基线（非 root/禁提权/资源限额/超时/只读 key）与无硬编码内网地址

运行: python3 -m unittest tests.test_worker_manager -v
"""
import importlib
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)


class TestParseBlpop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for k in ("REDIS_HOST", "WORKER_IMAGE"):
            os.environ.pop(k, None)
        import worker_manager
        cls.wm = importlib.reload(worker_manager)

    def test_raw_output(self):
        """管道模式：两行裸值。"""
        self.assertEqual(self.wm.parse_blpop("dev-flow:queue\ntask-20260730-001"),
                         "task-20260730-001")

    def test_interactive_output(self):
        """交互模式：带序号和引号。"""
        self.assertEqual(self.wm.parse_blpop('1) "dev-flow:queue"\n2) "task-abc"'),
                         "task-abc")

    def test_empty(self):
        self.assertIsNone(self.wm.parse_blpop(""))
        self.assertIsNone(self.wm.parse_blpop("\n\n"))


class TestPodSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import worker_manager
        cls.wm = importlib.reload(worker_manager)
        cls.spec = cls.wm.build_pod_spec("task-20260730-abc123", "ssh://git@example.com/u/r.git")

    def test_ephemeral_baseline(self):
        self.assertEqual(self.spec["spec"]["restartPolicy"], "Never")
        self.assertIn("activeDeadlineSeconds", self.spec["spec"])
        self.assertEqual(self.spec["metadata"]["labels"]["ephemeral"], "true")

    def test_security_baseline(self):
        sc = self.spec["spec"]["securityContext"]
        self.assertTrue(sc["runAsNonRoot"])
        c = self.spec["spec"]["containers"][0]["securityContext"]
        self.assertFalse(c["allowPrivilegeEscalation"])
        self.assertEqual(c["capabilities"]["drop"], ["ALL"])

    def test_resource_limits(self):
        res = self.spec["spec"]["containers"][0]["resources"]
        self.assertIn("limits", res)
        self.assertIn("requests", res)

    def test_ssh_key_readonly(self):
        vm = self.spec["spec"]["containers"][0]["volumeMounts"][0]
        self.assertTrue(vm["readOnly"])

    def test_repo_url_from_spec_not_hardcoded(self):
        envs = {e["name"]: e.get("value") for e in self.spec["spec"]["containers"][0]["env"]}
        self.assertEqual(envs["REPO_URL"], "ssh://git@example.com/u/r.git")
        self.assertEqual(envs["TASK_ID"], "task-20260730-abc123")

    def test_no_hardcoded_internal_addresses(self):
        """THESIS 诚实条款：镜像/base_url 必须来自 env 或公开默认，无内网 IP。"""
        import json
        blob = json.dumps(self.spec)
        self.assertNotIn("192.168.", blob)
        self.assertNotIn("bigmodel.cn", blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
