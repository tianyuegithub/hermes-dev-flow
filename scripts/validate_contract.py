#!/usr/bin/env python3
"""
validate_contract.py — 契约强制校验（PactFlow 核心）

Thesis: 契约必须可执行，否则不存在。
worker 产出的 output.json 不过校验 → 闸门直接判 FAILED，无评分可赦免。

零依赖设计：只实现本项目三份契约用到的 JSON Schema 子集
(type / required / properties / items / enum / const / minItems / maxItems)。
不引入 jsonschema 第三方库——可安装性优先，任何干净机器开箱即用。

用法:
  validate_contract.py <input|output|escalate> <json_file>
  validate_contract.py --task <task_id> <output|escalate>

退出码: 0=通过 / 1=违反契约 / 2=用法或文件错误
输出: JSON {"valid": bool, "errors": [...], "schema": "...", "file": "..."}
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CONTRACTS_DIR = paths.CONTRACTS_DIR
TASKS_DIR = paths.tasks_dir()

CONTRACT_NAMES = {
    "input": "input.schema.json",
    "output": "output.schema.json",
    "escalate": "escalate.schema.json",
}


# ── 零依赖 JSON Schema 子集校验器 ─────────────────────────────

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(instance, schema, path="$"):
    """递归校验，返回错误列表（空 = 通过）。只实现契约用到的关键字子集。"""
    errors = []

    # type
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPE_CHECKS.get(tt, lambda v: True)(instance) for tt in types):
            errors.append(f"{path}: 类型应为 {'/'.join(types)}，实际为 {type(instance).__name__}")
            return errors  # 类型不对，后续关键字无意义

    # const / enum
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: 值必须恒为 {schema['const']!r}，实际为 {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: 值 {instance!r} 不在允许范围 {schema['enum']}")

    # object
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: 缺少必填字段 '{req}'")
        props = schema.get("properties", {})
        for key, subschema in props.items():
            if key in instance and isinstance(subschema, dict):
                errors.extend(validate(instance[key], subschema, f"{path}.{key}"))

    # array
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: 数组至少 {schema['minItems']} 项，实际 {len(instance)} 项")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: 数组至多 {schema['maxItems']} 项，实际 {len(instance)} 项")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                errors.extend(validate(item, item_schema, f"{path}[{i}]"))

    return errors


# ── 契约加载与文件校验 ────────────────────────────────────────

def load_schema(name_or_path):
    """按契约名或文件路径加载 schema。"""
    if name_or_path in CONTRACT_NAMES:
        path = os.path.join(CONTRACTS_DIR, CONTRACT_NAMES[name_or_path])
        name = name_or_path
    else:
        path = name_or_path
        name = os.path.basename(path)
    with open(path) as f:
        return name, json.load(f)


def validate_file(name_or_path, file_path):
    """校验 JSON 文件，返回 (valid, errors, result_dict)。"""
    name, schema = load_schema(name_or_path)
    with open(file_path) as f:
        instance = json.load(f)
    errors = validate(instance, schema)
    return len(errors) == 0, errors, {
        "valid": len(errors) == 0,
        "errors": errors,
        "schema": name,
        "file": file_path,
    }


def validate_task_artifact(task_id, kind):
    """校验任务目录下的契约产物（output.json / escalate.json）。"""
    file_path = os.path.join(TASKS_DIR, task_id, f"{kind}.json")
    if not os.path.exists(file_path):
        return None, [f"文件不存在: {file_path}"], {
            "valid": None, "errors": [f"文件不存在: {file_path}"],
            "schema": kind, "file": file_path,
        }
    return validate_file(kind, file_path)


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        if len(args) == 3 and args[0] == "--task":
            _, _, result = validate_task_artifact(args[1], args[2])
        elif len(args) == 2:
            _, _, result = validate_file(args[0], args[1])
        else:
            print(__doc__)
            sys.exit(2)
    except FileNotFoundError as e:
        print(json.dumps({"valid": None, "errors": [f"文件不存在: {e.filename}"]}, ensure_ascii=False))
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(json.dumps({"valid": False, "errors": [f"JSON 解析失败: {e}"]}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["valid"] else 1)
