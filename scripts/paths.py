#!/usr/bin/env python3
"""
paths.py — 路径单一事实源（P0-1 可安装性，2026-07-30）

全项目唯一允许知道"根目录在哪"的模块。其他脚本一律经此取路径，
禁止再出现任何硬编码绝对路径。

解析规则:
  代码目录 (scripts/contracts/config) = 包安装目录，随本文件定位，不可覆盖
  数据目录 (tasks/worktrees)          = DEV_FLOW_HOME 环境变量 > 包安装目录

npm 全局安装、GitHub 直装、源码 checkout 下均开箱可用；
测试用 DEV_FLOW_HOME 指向临时目录即可完全隔离。
"""
import os

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PACKAGE_DIR, "scripts")
CONTRACTS_DIR = os.path.join(PACKAGE_DIR, "contracts")
CONFIG_DIR = os.path.join(PACKAGE_DIR, "config")


def home() -> str:
    """数据根目录：DEV_FLOW_HOME env > 包安装目录。"""
    return os.environ.get("DEV_FLOW_HOME", PACKAGE_DIR)


def tasks_dir() -> str:
    return os.path.join(home(), ".hermes", "tasks")


def task_dir(task_id: str) -> str:
    return os.path.join(tasks_dir(), task_id)


def worktrees_dir() -> str:
    return os.path.join(home(), "worktrees")


def script(name: str) -> str:
    """包内脚本绝对路径（代码位置，不受 DEV_FLOW_HOME 影响）。"""
    return os.path.join(SCRIPTS_DIR, name)


def contract(name: str) -> str:
    """契约 schema 绝对路径。name: input / output / escalate（可省 .schema.json）。"""
    if not name.endswith(".json"):
        name = f"{name}.schema.json"
    return os.path.join(CONTRACTS_DIR, name)


def pref_table() -> str:
    """编排偏好路由表路径。"""
    return os.path.join(CONFIG_DIR, "orchestration-preferences.json")
