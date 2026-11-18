"""Owner rule: no function in src/recruitai longer than 100 lines."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "recruitai"
MAX_LINES = 100


def test_no_function_is_longer_than_100_lines() -> None:
    too_long = [
        f"{path.relative_to(SRC)}:{node.lineno} {node.name} {length}"
        for path in sorted(SRC.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (length := (node.end_lineno or node.lineno) - node.lineno + 1) > MAX_LINES
    ]
    assert not too_long, "functions over 100 lines:\n" + "\n".join(too_long)
