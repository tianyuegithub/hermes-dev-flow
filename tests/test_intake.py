#!/usr/bin/env python3
"""
test_intake.py — intake.py 分类准确性测试
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

def test_classify_feature():
    """测试 feature 类型识别"""
    from intake import classify

    # 加 / 新增 / 实现 → feature
    assert classify("deer-flow 加一个 /health 接口")["task_type"] == "feature"
    assert classify("新增用户登录功能")["task_type"] == "feature"
    assert classify("实现导出 CSV 接口")["task_type"] == "feature"

def test_classify_bug():
    """测试 bug 类型识别"""
    from intake import classify
    assert classify("修一下登录页面的 bug")["task_type"] == "bug"
    assert classify("修复编译错误")["task_type"] == "bug"
    assert classify("这个报错不管用")["task_type"] == "bug"

def test_classify_doc():
    """测试 doc 类型识别"""
    from intake import classify
    assert classify("更新 README 文档")["task_type"] == "doc"

def test_classify_risk():
    """测试风险等级识别"""
    from intake import classify
    assert classify("修改数据库 schema")["risk"] == "high"
    assert classify("修改数据库权限密码")["risk"] == "high"
    assert classify("加一个接口")["risk"] == "medium"

def test_classify_repo_matching():
    """测试仓库 triggers 匹配"""
    from intake import classify
    result = classify("deer-flow 加个功能")
    assert result["repo_key"] == "deer-flow"

    result = classify("灵境改一下首页")
    assert result["repo_key"] == "deer-flow"

def test_classify_gates():
    """测试闸门生成"""
    from intake import classify
    assert "方案" in classify("加新功能")["gates"]
    assert "验证" in classify("改文案")["gates"]
    assert "架构" in classify("改数据库 schema")["gates"]

if __name__ == "__main__":
    test_classify_feature()
    test_classify_bug()
    test_classify_doc()
    test_classify_risk()
    test_classify_repo_matching()
    test_classify_gates()
    print("✅ intake.py: 6/6 测试通过")
