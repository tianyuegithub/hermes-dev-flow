#!/usr/bin/env python3
"""
mini_yaml.py — PyYAML 的零依赖兜底（仅支持本框架配置文件的子集）

支持：两层嵌套字典、字符串列表、标量（str/int/float/bool）、# 注释。
刻意不支持：锚点、多行字符串、流式语法、深层嵌套——配置文件超出子集时
应安装 PyYAML，本模块会抛错提醒，绝不静默错读。

用法:
  try:
      import yaml
  except ImportError:
      import mini_yaml as yaml
"""


def _parse_scalar(s: str):
    s = s.strip()
    if not s:
        return ""
    if s in ("[]", "{}"):
        return [] if s == "[]" else {}
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        return s[1:-1]
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1]
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    if s.startswith("[") and s.endswith("]"):  # 行内列表 [a, b, c]
        inner = s[1:-1].strip()
        return [_parse_scalar(x) for x in inner.split(",")] if inner else []
    return s


def safe_load(text):
    """解析缩进式 YAML 子集。text 为 str 或文件对象。"""
    if hasattr(text, "read"):
        text = text.read()
    root = {}
    # 栈: (indent, container_dict)
    stack = [(-1, root)]
    last_key_at_indent = {}  # indent -> (dict, key)，用于挂载列表项

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("- "):
            # 列表项：挂到上一层最后一个 key
            ctx = last_key_at_indent.get(indent - 2)
            if ctx is None:
                raise ValueError(f"mini_yaml 不支持的列表位置 (行 {lineno}): {raw!r}")
            d, k = ctx
            if not isinstance(d.get(k), list):
                d[k] = []
            d[k].append(_parse_scalar(stripped[2:]))
            continue

        if ":" not in stripped:
            raise ValueError(f"mini_yaml 不支持此行 (行 {lineno}): {raw!r}")
        key, _, val = stripped.partition(":")
        key = key.strip().strip('"').strip("'")
        val = val.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if val == "":
            # 可能是嵌套 dict 或列表（列表由后续 '- ' 行创建）
            child = {}
            parent[key] = child
            last_key_at_indent[indent] = (parent, key)
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(val)
            last_key_at_indent[indent] = (parent, key)

    return root


def _dump_dict(d: dict, indent: int, lines: list):
    pad = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            _dump_dict(v, indent + 1, lines)
        elif isinstance(v, list):
            if not v:
                lines.append(f"{pad}{k}: []")
            else:
                lines.append(f"{pad}{k}:")
                for item in v:
                    lines.append(f"{pad}  - {_format_scalar(item)}")
        else:
            lines.append(f"{pad}{k}: {_format_scalar(v)}")


def _format_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if not s or s != s.strip() or any(c in s for c in ':#"\'') or s.lower() in (
            "true", "false", "yes", "no", "null", "~"):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def dump(data, allow_unicode=True, default_flow_style=False):
    """输出缩进式 YAML 字符串（与 PyYAML dump 的常用调用形态兼容）。"""
    lines = []
    _dump_dict(data, 0, lines)
    return "\n".join(lines) + "\n"
