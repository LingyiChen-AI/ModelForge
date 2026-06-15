"""{{ name }} 模板参数:抽取与语法校验。
app-server 用于 Prompt 保存校验;train-worker 在 Prompt 评测阶段复用(render 留给子项目 C)。
"""
from __future__ import annotations

import re

__all__ = ["extract_params", "validate_template", "render"]

# {{ name }} —— 两侧空格可选;name = 字母/数字/下划线/中文
_PARAM_RE = re.compile(r"\{\{\s*([\w一-鿿]+)\s*\}\}")
# 任意一对不含花括号的 {{ ... }}(用于校验)
_PAIR_RE = re.compile(r"\{\{([^{}]*)\}\}")
_NAME_RE = re.compile(r"[\w一-鿿]+")


def extract_params(text: str) -> list[str]:
    """抽出全部 {{ name }} 的 name(去重保序)。"""
    seen: dict[str, None] = {}
    for m in _PARAM_RE.finditer(text or ""):
        seen.setdefault(m.group(1), None)
    return list(seen)


def validate_template(text: str) -> list[str]:
    """返回错误消息列表(空 = 合法)。"""
    text = text or ""
    errors: list[str] = []
    for m in _PAIR_RE.finditer(text):
        inner = m.group(1).strip()
        if not inner:
            errors.append("存在空参数 {{ }},请填写参数名")
        elif not _NAME_RE.fullmatch(inner):
            errors.append(f"参数名非法:{{{{ {inner} }}}}(只允许字母/数字/下划线/中文)")
    residual = _PAIR_RE.sub("", text)
    if "{{" in residual or "}}" in residual:
        errors.append("花括号不成对或嵌套(请用 {{ 参数名 }})")
    out: list[str] = []
    for e in errors:
        if e not in out:
            out.append(e)
    return out


def render(template: str, values: dict) -> str:
    """把 {{ name }} 替换为 str(values.get(name, ""));None / 缺失 → 空串。"""
    def _sub(m):
        v = values.get(m.group(1))
        return "" if v is None else str(v)
    return _PARAM_RE.sub(_sub, template or "")
