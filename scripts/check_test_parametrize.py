#!/usr/bin/env python3
# Wave 5-1 — pytest test ファイルで 3+ iteration の手書き for-loop を detect し、
# @pytest.mark.parametrize 化を推奨する warning hook。
#
# Why: PR 内で同一 assert pattern を for-loop で 3+ 回繰り返す test は、
#   個別 failure 報告 (test_X[case1] / test_X[case2]) が出ないため debug が
#   困難。 parametrize 化で individual case ごとの failure trace が得られる。
#   既存 parametrize 利用 test には影響しない (`@pytest.mark.parametrize`
#   decorator 付きの function 内 loop は false positive のため skip)。
#
# How to apply: warning-only。 block しない (legacy test を一斉に書き換える
#   churn を避ける)。 新規 test 追加時に PR review で気付ける hint として機能。

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Test root candidates — pytest collects from these.
TEST_ROOTS = [
    ROOT / "src" / "python" / "tests",
    ROOT / "src" / "python_run" / "tests",
    ROOT / "tests",
]

# Threshold: for-loop が assert を含み 3+ iteration 想定 (literal list/tuple)
ITERATION_THRESHOLD = 3


def _function_has_parametrize(node: ast.FunctionDef) -> bool:
    """@pytest.mark.parametrize decorator が付いているか確認。"""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Attribute) and func.attr == "parametrize":
                return True
        elif isinstance(dec, ast.Attribute) and dec.attr == "parametrize":
            return True
    return False


def _loop_iter_size(node: ast.For) -> int | None:
    """for-loop の iterable が literal list/tuple なら element 数を返す。

    list/tuple 以外 (e.g. range / dict.items / generator) は None — 静的に判定
    できないため safe-side で skip。
    """
    iter_node = node.iter
    if isinstance(iter_node, (ast.List, ast.Tuple)):
        return len(iter_node.elts)
    return None


def _loop_has_assert(node: ast.For) -> bool:
    """for-loop body 内に `assert` または pytest.raises 等 assertion 系が
    存在するか。 単純な data initialization loop を除外。"""
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            # pytest.raises / pytest.warns / self.assertEqual 等
            func = child.func
            if isinstance(func, ast.Attribute):
                if func.attr in ("raises", "warns") or func.attr.startswith("assert"):
                    return True
    return False


def _scan_file(path: Path) -> list[tuple[int, str, int]]:
    """File を AST parse し、 candidate (line, func_name, iter_size) を返す。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    findings: list[tuple[int, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        if _function_has_parametrize(node):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.For):
                continue
            size = _loop_iter_size(child)
            if size is None or size < ITERATION_THRESHOLD:
                continue
            if not _loop_has_assert(child):
                continue
            findings.append((child.lineno, node.name, size))
    return findings


def main() -> int:
    files_to_scan: list[Path] = []
    for root in TEST_ROOTS:
        if not root.exists():
            continue
        files_to_scan.extend(root.rglob("test_*.py"))

    total_findings = 0
    for path in sorted(files_to_scan):
        findings = _scan_file(path)
        if not findings:
            continue
        rel = path.relative_to(ROOT)
        for lineno, func, size in findings:
            print(
                f"::warning file={rel},line={lineno}::"
                f"test {func} contains for-loop with {size} literal iterations "
                f"and assertions — consider @pytest.mark.parametrize for "
                f"per-case failure isolation"
            )
            total_findings += 1

    if total_findings:
        print(
            f"\n[check_test_parametrize] {total_findings} candidate(s) found "
            f"across {len(files_to_scan)} test file(s). Warning-only, not blocking.",
            file=sys.stderr,
        )
    # warning-only — always exit 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
