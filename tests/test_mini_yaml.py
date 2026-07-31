#!/usr/bin/env python3
"""
test_mini_yaml.py — 零依赖 YAML 兜底子集的契约测试

保证 mini_yaml 在本框架配置文件的实际形态上与 PyYAML 行为一致。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mini_yaml


SAMPLE = """
# 注释行
claude:
  base_url: "https://open.bigmodel.cn/api/anthropic"
  api_key: "sk-test-123"
repo:
  url: "ssh://git@host:30022/owner/repo.git"
  default_branch: main
  triggers:
    - deer-flow
    - 灵境
redis:
  host: 192.168.31.173
  port: 32319
worker:
  max_turns: 30
  max_budget_usd: 1.5
  enabled: true
empty_list: []
inline_list: [a, b, c]
"""


class TestMiniYaml(unittest.TestCase):
    def test_nested_dict(self):
        d = mini_yaml.safe_load(SAMPLE)
        self.assertEqual(d["claude"]["base_url"], "https://open.bigmodel.cn/api/anthropic")
        self.assertEqual(d["repo"]["default_branch"], "main")

    def test_scalars(self):
        d = mini_yaml.safe_load(SAMPLE)
        self.assertEqual(d["redis"]["port"], 32319)          # int
        self.assertEqual(d["worker"]["max_budget_usd"], 1.5)  # float
        self.assertIs(d["worker"]["enabled"], True)           # bool
        self.assertEqual(d["redis"]["host"], "192.168.31.173")  # 非 float 的带点字符串

    def test_lists(self):
        d = mini_yaml.safe_load(SAMPLE)
        self.assertEqual(d["repo"]["triggers"], ["deer-flow", "灵境"])
        self.assertEqual(d["empty_list"], [])
        self.assertEqual(d["inline_list"], ["a", "b", "c"])

    def test_roundtrip_dump(self):
        d = mini_yaml.safe_load(SAMPLE)
        d2 = mini_yaml.safe_load(mini_yaml.dump(d))
        self.assertEqual(d, d2)

    def test_real_config_parseable(self):
        """真实的 ~/.hermes/dev-flow/config.yaml 必须能被兜底解析。"""
        path = os.path.expanduser("~/.hermes/dev-flow/config.yaml")
        if not os.path.exists(path):
            self.skipTest("无真实配置文件")
        d = mini_yaml.safe_load(open(path))
        self.assertIn("claude", d)
        self.assertIsInstance(d.get("repo", {}).get("triggers", []), list)

    def test_unsupported_line_raises(self):
        with self.assertRaises(ValueError):
            mini_yaml.safe_load("key_without_colon_line")


if __name__ == "__main__":
    unittest.main()
