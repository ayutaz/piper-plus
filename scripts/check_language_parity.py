#!/usr/bin/env python3
"""Language list 3-way parity gate (WebUI / CLI / FastAPI test fixture).

Three independent language-list declarations live in this repo:

  1. ``docker/webui/app.py``               SAMPLE_TEXTS dict keys
  2. ``docker/python-inference/inference.py``  argparse ``--language choices=[...]``
  3. ``docker/python-inference/test_openai_api.py``  assertion against
     ``/v1/audio/speech/languages`` endpoint response

The FastAPI endpoint itself reads ``engine.language_id_map`` dynamically
from the loaded model config, so it cannot be statically compared without
a model. We instead pin the endpoint's *test assertion* — when a developer
adds/removes a language they must update WebUI sample texts, CLI choices,
**and** the OpenAI API test assertion together.

Drift between any of these three has happened in the past (PR #2f4efaf9
fixed a WebUI/CLI drift where the WebUI listed 7 languages but the CLI
choices accepted only 6). This gate prevents regression.

Usage:
    python scripts/check_language_parity.py

Exit codes:
    0 -- all three sources agree on the language set
    1 -- drift detected (lists each source and the language set found)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

WEBUI_PATH = REPO_ROOT / "docker" / "webui" / "app.py"
CLI_PATH = REPO_ROOT / "docker" / "python-inference" / "inference.py"
TEST_PATH = REPO_ROOT / "docker" / "python-inference" / "test_openai_api.py"


def _extract_sample_texts_keys(path: Path) -> list[str] | None:
    """Parse ``SAMPLE_TEXTS = {...}`` and return its string keys, in source order."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "SAMPLE_TEXTS"
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        keys: list[str] = []
        for k in node.value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.append(k.value)
        return keys
    return None


def _extract_cli_language_choices(path: Path) -> list[str] | None:
    """Parse argparse ``parser.add_argument("--language", choices=[...])``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (
            isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"
        ):
            continue
        if not (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "--language"
        ):
            continue
        for kw in node.keywords:
            if kw.arg == "choices" and isinstance(kw.value, ast.List):
                return [
                    e.value
                    for e in kw.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                ]
    return None


def _extract_test_assertion_languages(path: Path) -> list[str] | None:
    """Parse the canonical assertion ``data["languages"] == ["en", "es", ...]``.

    Looks for the literal list on the RHS of an Eq comparison whose LHS is a
    subscript expression with the literal string key ``"languages"``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not (len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)):
            continue
        left = node.left
        if not (
            isinstance(left, ast.Subscript)
            and isinstance(left.slice, ast.Constant)
            and left.slice.value == "languages"
        ):
            continue
        rhs = node.comparators[0]
        if not isinstance(rhs, ast.List):
            continue
        return [
            e.value
            for e in rhs.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    return None


def main() -> int:
    webui_langs = _extract_sample_texts_keys(WEBUI_PATH)
    cli_langs = _extract_cli_language_choices(CLI_PATH)
    test_langs = _extract_test_assertion_languages(TEST_PATH)

    errors: list[str] = []
    if webui_langs is None:
        errors.append(f"  SAMPLE_TEXTS dict not found in {WEBUI_PATH.relative_to(REPO_ROOT)}")
    if cli_langs is None:
        errors.append(f"  --language choices=[...] not found in {CLI_PATH.relative_to(REPO_ROOT)}")
    if test_langs is None:
        errors.append(
            f"  data[\"languages\"] == [...] assertion not found in "
            f"{TEST_PATH.relative_to(REPO_ROOT)}"
        )
    if errors:
        print("ERROR: failed to extract one or more language declarations:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    # Compare as sets (order is canonicalized differently in each source).
    assert webui_langs is not None
    assert cli_langs is not None
    assert test_langs is not None

    webui_set = set(webui_langs)
    cli_set = set(cli_langs)
    test_set = set(test_langs)

    if webui_set == cli_set == test_set:
        print(
            f"OK: WebUI / CLI / FastAPI-test agree on {len(webui_set)} languages: "
            f"{sorted(webui_set)}"
        )
        return 0

    print("ERROR: language list drift across 3 sources", file=sys.stderr)
    print(
        f"  WebUI  ({WEBUI_PATH.relative_to(REPO_ROOT)} SAMPLE_TEXTS): "
        f"{sorted(webui_set)} (size={len(webui_set)})",
        file=sys.stderr,
    )
    print(
        f"  CLI    ({CLI_PATH.relative_to(REPO_ROOT)} --language choices): "
        f"{sorted(cli_set)} (size={len(cli_set)})",
        file=sys.stderr,
    )
    print(
        f"  Test   ({TEST_PATH.relative_to(REPO_ROOT)} /v1/audio/speech/languages assertion): "
        f"{sorted(test_set)} (size={len(test_set)})",
        file=sys.stderr,
    )

    only_webui = webui_set - (cli_set | test_set)
    only_cli = cli_set - (webui_set | test_set)
    only_test = test_set - (webui_set | cli_set)
    if only_webui:
        print(f"  Only in WebUI: {sorted(only_webui)}", file=sys.stderr)
    if only_cli:
        print(f"  Only in CLI: {sorted(only_cli)}", file=sys.stderr)
    if only_test:
        print(f"  Only in Test: {sorted(only_test)}", file=sys.stderr)

    print(
        "\nFix: synchronize all three sources. When adding/removing a language, update:\n"
        f"  1. {WEBUI_PATH.relative_to(REPO_ROOT)}:SAMPLE_TEXTS\n"
        f"  2. {CLI_PATH.relative_to(REPO_ROOT)}: parser.add_argument('--language', choices=[...])\n"
        f"  3. {TEST_PATH.relative_to(REPO_ROOT)}: data['languages'] == [...] assertion (alphabetical)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
