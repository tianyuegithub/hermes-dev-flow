#!/usr/bin/env python3
"""
test_state_machine.py — state.py 状态机单元测试
"""
import os, sys, json, tempfile, shutil

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

TASKS_DIR = tempfile.mkdtemp()

def setup():
    """每个测试前设置 TASKS_DIR"""
    import state
    state.BASE_DIR = TASKS_DIR
    state.QUIET = True

def teardown():
    shutil.rmtree(TASKS_DIR, ignore_errors=True)

def test_init_and_get():
    """测试 init + get 基本流程"""
    import state
    state.cmd_init("test-1", "feature", "git@example.com/repo.git")
    data = state.load("test-1")
    assert data["status"] == "CREATED"
    assert data["task_type"] == "feature"
    assert data["spec_version"] == 1

def test_valid_transitions():
    """测试合法状态转换"""
    import state
    state.cmd_init("test-2", "bug", "git@example.com/repo.git")

    # 合法: CREATED → GATE_PENDING
    data = state.load("test-2")
    data["status"] = "GATE_PENDING"
    state.save("test-2", data)
    assert state.load("test-2")["status"] == "GATE_PENDING"

    # 合法: GATE_PENDING → EXECUTING
    data = state.load("test-2")
    data["status"] = "EXECUTING"
    state.save("test-2", data)
    assert state.load("test-2")["status"] == "EXECUTING"

def test_invalid_transition():
    """测试非法状态转换被拒绝"""
    import state
    state.cmd_init("test-3", "doc", "git@example.com/repo.git")

    # 非法: CREATED → DONE
    try:
        old_allowed = state.VALID_TRANSITIONS.get("CREATED", [])
        # 直接调 cmd_trans 会检查合法性
        state.cmd_trans("test-3", "DONE")
        assert False, "应该拒绝 CREATED → DONE"
    except SystemExit:
        pass  # 预期行为：state.py 拒绝非法转换

def test_set_field():
    """测试 set 命令"""
    import state
    state.cmd_init("test-4", "feature", "git@example.com/repo.git")
    state.cmd_set("test-4", "worker", '"claude"')
    data = state.load("test-4")
    assert data["worker"] == "claude"

def test_spec_version_and_gate_history():
    """测试冻结引擎字段"""
    import state
    state.cmd_init("test-5", "feature", "git@example.com/repo.git")
    data = state.load("test-5")
    assert data["spec_version"] == 1
    assert data["gate_history"] == []

if __name__ == "__main__":
    test_init_and_get()
    test_valid_transitions()
    test_invalid_transition()
    test_set_field()
    test_spec_version_and_gate_history()
    shutil.rmtree(TASKS_DIR, ignore_errors=True)
    print("✅ state.py: 5/5 测试通过")
