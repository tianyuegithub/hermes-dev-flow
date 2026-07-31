#!/usr/bin/env python3
"""
dev_flow_config.py — 统一的配置读取模块
所有脚本通过这个模块读配置，不硬编码任何凭据/地址。

配置优先级:
  1. 环境变量 (DEVFLOW_XXX)
  2. ~/.hermes/dev-flow/config.yaml
  3. config/config.defaults.yaml (内置默认值)
"""
import os

try:
    import yaml
except ImportError:  # 零依赖兜底：仅支持本框架配置文件子集
    import mini_yaml as yaml

CONFIG_PATH = os.path.expanduser("~/.hermes/dev-flow/config.yaml")

_defaults = {
    "claude": {
        "base_url": "https://open.bigmodel.cn/api/anthropic",
        "api_key": "",
    },
    "openai": {"api_key": ""},
    "repo": {
        "url": "",
        "clone_url": "",
        "default_branch": "main",
        "platform": "gitea",
        "triggers": [],
    },
    "gitea": {"url": "", "api_url": "", "owner": "", "repo_name": ""},
    "redis": {"host": "127.0.0.1", "port": 6379, "internal_host": "127.0.0.1", "internal_port": 6379},
    "k8s": {"namespace": "dev-flow", "deployment": "dev-flow-worker", "image": ""},
    "worker": {"max_turns": 30, "max_budget_usd": 1.50, "heartbeat_interval": 30, "heartbeat_ttl": 60},
    "paths": {
        "tasks_dir": "~/.hermes/dev-flow/tasks",
        "worktrees_dir": "~/.hermes/dev-flow/worktrees",
        "scripts_dir": "~/.hermes/dev-flow/scripts",
    },
}


def load_config():
    """加载配置，合并默认值。"""
    config = dict(_defaults)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            user_config = yaml.safe_load(f) or {}
        for section in _defaults:
            if section in user_config:
                if isinstance(user_config[section], dict):
                    config[section].update(user_config[section])
                else:
                    config[section] = user_config[section]
    return config


# 全局单例
_config = None


def get(key_path: str, default=None):
    """按路径读配置值。例如 get('redis.host')"""
    global _config
    if _config is None:
        _config = load_config()
    parts = key_path.split(".")
    val = _config
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return default
    return val if val is not None else default


def get_path(key_path: str):
    """读路径类配置，自动展开 ~"""
    val = get(key_path, "")
    return os.path.expanduser(val) if val else val


if __name__ == "__main__":
    cfg = load_config()
    print(yaml.dump(cfg, allow_unicode=True, default_flow_style=False))
