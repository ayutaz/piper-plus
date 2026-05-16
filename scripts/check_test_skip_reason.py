#!/usr/bin/env python3
"""Require ``reason=...`` on every Python test skip.

Background:
    The repo has ~139 ``@pytest.mark.skip`` / ``pytest.skip(...)`` calls in
    ``src/python/tests/`` and ``src/python_run/tests/``. A subset of them
    have no ``reason=`` argument, which means:

      - ``pytest -v`` shows them as "SKIPPED" with an empty justification.
      - Reviewers can't tell whether a skip is permanent (dependency missing
        in CI), temporary (waiting on a fix), or accidental (someone testing
        locally and forgot to remove the decorator).
      - When the skip eventually becomes unnecessary, no one knows.

This script statically parses test files (no imports executed) and flags
any of:

    @pytest.mark.skip()                              # bare
    @pytest.mark.skip                                 # decorator-without-call
    @pytest.mark.skipif(condition)                    # 1-arg, no reason
    pytest.skip("foo")                                # OK: positional message
    pytest.skip()                                     # FAIL: empty
    pytest.skip(reason="bar")                         # OK: kwarg
    pytestmark = pytest.mark.skip                     # FAIL: module-level bare

Detection is conservative: missing reason on a skipif's *first* arg
(condition) is acceptable; only the absence of a reason kwarg or string
arg matters.

Exit codes:
    0 -- every skip has a non-empty reason
    1 -- one or more skips lack a reason

Scope:
    By default, runs on staged Python files passed via argv (the pre-commit
    convention). When run with no argv, walks all ``src/**/tests/**/*.py``
    files.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Glob roots for full-repo scan fallback.
TEST_ROOTS: tuple[str, ...] = (
    "src/python/tests",
    "src/python_run/tests",
    "src/python/g2p/tests",
)


def _is_pytest_skip_attr(node: ast.AST, names: tuple[str, ...]) -> bool:
    """Return True if ``node`` is ``pytest.<name>`` or ``pytest.mark.<name>``
    for any ``<name>`` in ``names``.
    """
    if isinstance(node, ast.Attribute) and node.attr in names:
        # pytest.skip / pytest.mark.skip
        if isinstance(node.value, ast.Name) and node.value.id == "pytest":
            return True
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "mark"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "pytest"
        ):
            return True
    return False


def _has_nonempty_reason_kwarg(call: ast.Call) -> bool:
    """Return True if ``call`` has a ``reason=...`` kwarg with non-empty value.

    Accepts plain strings, f-strings (``ast.JoinedStr``), and any other
    expression — only an empty literal string is rejected. Variables /
    function calls / expressions are assumed to evaluate to a meaningful
    reason; we can't determine that statically.
    """
    for kw in call.keywords:
        if kw.arg != "reason":
            continue
        val = kw.value
        # Empty literal "" → not a reason.
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            return bool(val.value.strip())
        # f-string / variable / expression → assume meaningful.
        return True
    return False


def _call_has_reason(call: ast.Call, kind: str) -> bool:
    """Return True if a skip-like call has a non-empty reason.

    ``kind`` is ``"skip"`` or ``"skipif"``.

    - For ``skip``: any positional arg (string / f-string / expr) OR
      ``reason=`` kwarg with non-empty value.
    - For ``skipif``: must have ``reason=`` kwarg (positional[0] is condition).
    """
    if _has_nonempty_reason_kwarg(call):
        return True
    if kind == "skipif":
        return False
    # skip with positional argument — accept any non-empty literal,
    # any f-string, or any expression. Only `pytest.skip()` with zero
    # args (or an empty literal) fails.
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return bool(first.value.strip())
        # Non-string constant, f-string, name, call, etc. — accept.
        return True
    return False


def _check_file(path: Path) -> list[tuple[int, str]]:
    """Return list of ``(line_no, snippet)`` for every reasonless skip."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []

    violations: list[tuple[int, str]] = []
    source_lines = text.splitlines()

    def snippet(lineno: int) -> str:
        idx = lineno - 1
        if 0 <= idx < len(source_lines):
            return source_lines[idx].strip()
        return ""

    for node in ast.walk(tree):
        # 1. Decorator usage: @pytest.mark.skip(...) / @pytest.mark.skipif(...)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                # Decorator could be Call or bare Attribute.
                if isinstance(dec, ast.Call):
                    func = dec.func
                    if _is_pytest_skip_attr(func, ("skip",)):
                        if not _call_has_reason(dec, "skip"):
                            violations.append((dec.lineno, snippet(dec.lineno)))
                    elif _is_pytest_skip_attr(func, ("skipif",)):
                        if not _call_has_reason(dec, "skipif"):
                            violations.append((dec.lineno, snippet(dec.lineno)))
                else:
                    # @pytest.mark.skip  (no call -> definitely no reason)
                    if _is_pytest_skip_attr(dec, ("skip",)):
                        violations.append((dec.lineno, snippet(dec.lineno)))

        # 2. Module-level: pytestmark = pytest.mark.skip(...)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "pytestmark",
                }:
                    val = node.value
                    if isinstance(val, ast.Call):
                        if _is_pytest_skip_attr(val.func, ("skip",)):
                            if not _call_has_reason(val, "skip"):
                                violations.append((val.lineno, snippet(val.lineno)))
                        elif _is_pytest_skip_attr(val.func, ("skipif",)):
                            if not _call_has_reason(val, "skipif"):
                                violations.append((val.lineno, snippet(val.lineno)))
                    elif _is_pytest_skip_attr(val, ("skip",)):
                        violations.append((val.lineno, snippet(val.lineno)))

        # 3. Inline call: pytest.skip(...)
        if isinstance(node, ast.Call):
            func = node.func
            if _is_pytest_skip_attr(func, ("skip",)):
                if not _call_has_reason(node, "skip"):
                    violations.append((node.lineno, snippet(node.lineno)))

    return violations


def _gather_paths(argv: list[str]) -> list[Path]:
    """Resolve paths from argv (pre-commit) or test roots (manual)."""
    if argv:
        return [Path(p) for p in argv if p.endswith(".py")]
    paths: list[Path] = []
    for root in TEST_ROOTS:
        base = REPO_ROOT / root
        if base.exists():
            paths.extend(base.rglob("test_*.py"))
            paths.extend(base.rglob("*_test.py"))
    return paths


def main(argv: list[str]) -> int:
    paths = _gather_paths(argv)
    if not paths:
        return 0

    failures: list[tuple[str, int, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        # Only check files inside a tests/ directory.
        if "tests" not in path.parts and "test" not in path.parts:
            continue
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = str(path)
        for line_no, snippet in _check_file(path):
            failures.append((rel, line_no, snippet))

    if not failures:
        print(
            f"OK: scanned {len(paths)} test file(s); every pytest skip has "
            "a non-empty reason."
        )
        return 0

    print(
        f"ERROR: {len(failures)} pytest skip(s) without a `reason=` argument:",
        file=sys.stderr,
    )
    for rel, line_no, snippet in failures:
        print(f"  {rel}:{line_no}: {snippet}", file=sys.stderr)
    print(
        "\nWhy: skips without reasons accumulate as silent technical debt. "
        "Reviewers can't tell if the skip is temporary, permanent, or "
        "accidental. Every skip should self-document.",
        file=sys.stderr,
    )
    print(
        "\nFix: add a reason. Examples:",
        file=sys.stderr,
    )
    print(
        '  @pytest.mark.skip(reason="requires pyopenjtalk-plus, optional in CI")',
        file=sys.stderr,
    )
    print(
        '  @pytest.mark.skipif(sys.platform == "win32", reason="ONNX RT path mismatch on Windows")',
        file=sys.stderr,
    )
    print(
        '  pytest.skip("Japanese phonemizer not available")',
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
