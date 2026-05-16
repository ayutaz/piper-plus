#!/usr/bin/env python3
# Wave 5-14 — 学習 CLI 引数 drift check (Template A/B vs argparse).
#
# Why: CLAUDE.md の Template A (事前学習) / Template B (FT) は最新の
#   `python -m piper_train ...` 推奨呼び出しを記述する。 argparse 側で
#   引数 rename / 削除があると Template が silent に invalid になり、
#   user がコピペで学習開始 → 起動失敗を踏む。 本 gate は「Template 内で
#   使用される引数名が argparse に**存在する**」 ことを pin する narrow
#   contract gate (value drift ではなく argument-name drift)。
#
# How to apply: pre-commit / CI gate。 src/python/piper_train/__main__.py を
#   AST parse して全 argparse argument 名を集計、 CLAUDE.md の Template A/B
#   コードブロック内の `--arg-name` を grep。 未知の引数があれば fail。

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# argparse args が登録される source file。 VitsModel.add_model_specific_args 経由で
# `--batch-size` 等が追加されるため、 __main__.py と lightning.py の両方を scan する。
SOURCE_FILES = [
    ROOT / "src" / "python" / "piper_train" / "__main__.py",
    ROOT / "src" / "python" / "piper_train" / "vits" / "lightning.py",
]
CLAUDE_MD = ROOT / "CLAUDE.md"

# Template コードブロック開始 marker。 CLAUDE.md 内で
# `### Template A` / `### Template B` の section から
# 次の `### ` までを Template 範囲とする。
TEMPLATE_SECTION_RE = re.compile(
    r"###\s*Template\s*[AB][^\n]*\n(.*?)(?=###\s|\Z)", re.DOTALL
)
# 引数: `--word` または `--word-with-dash` (POSIX kebab + underscore)。
# 値は引数の次 token (= ではなく space separator) で省略可。
ARG_RE = re.compile(r"--([A-Za-z][A-Za-z0-9_\-]*)")


def _collect_argparse_args(path: Path) -> set[str]:
    """argparse `add_argument("--foo", "--bar", ...)` を全部抽出。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"::error file={path}::Python parse failed: {e}")
        return set()

    args: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            continue
        if name != "add_argument":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith("--"):
                    args.add(arg.value[2:])
    return args


def _collect_template_args(path: Path) -> set[str]:
    """CLAUDE.md の Template A/B コードブロックから --arg を抽出。"""
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    template_args: set[str] = set()
    for match in TEMPLATE_SECTION_RE.finditer(text):
        section = match.group(1)
        # ```bash ... ``` フェンス内に絞り込む
        for fenced in re.finditer(r"```[a-z]*\n(.*?)```", section, re.DOTALL):
            code = fenced.group(1)
            for arg_match in ARG_RE.finditer(code):
                template_args.add(arg_match.group(1))
    return template_args


def main() -> int:
    for src in SOURCE_FILES:
        if not src.exists():
            print(f"::error::{src} not found", file=sys.stderr)
            return 1
    if not CLAUDE_MD.exists():
        print(f"::warning::{CLAUDE_MD} not found, skip", file=sys.stderr)
        return 0

    argparse_args: set[str] = set()
    for src in SOURCE_FILES:
        argparse_args.update(_collect_argparse_args(src))
    template_args = _collect_template_args(CLAUDE_MD)

    if not template_args:
        print("[check_training_defaults] no Template A/B fences found, skip")
        return 0

    # PyTorch Lightning が自動追加する引数 / abbreviated form は本 gate の
    # 対象外 (e.g. --help は argparse 内蔵)。 但し Template に頻出する
    # core 学習引数のみ check する。
    lightning_or_builtin = {
        "help", "version",
        # PyTorch Lightning Trainer 自動引数の主要なもの
        "accelerator", "devices", "precision", "strategy", "max_epochs",
        "default_root_dir", "limit-val-batches",
    }

    unknown = sorted(
        arg for arg in template_args
        if arg not in argparse_args and arg not in lightning_or_builtin
    )

    if unknown:
        print("::error::Training Template references unknown CLI flags:")
        for arg in unknown:
            print(f"  - --{arg}")
        print()
        print(
            f"These flags appear in CLAUDE.md Template A / Template B but are "
            f"not registered in any of the scanned argparse files. Update "
            f"CLAUDE.md or restore the argparse entry. Scanned: "
            f"{', '.join(str(s.relative_to(ROOT)) for s in SOURCE_FILES)}."
        )
        return 1

    print(
        f"[check_training_defaults] OK — {len(template_args)} Template flag(s) "
        f"all resolved against {len(argparse_args)} argparse entries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
