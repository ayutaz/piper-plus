#!/usr/bin/env python3
"""README / docs code block example validation gate.

PR #493 で WASM の README が `synthesizeFromReferenceAudio` の引数を
``referenceAudio / speakerEncoderModel`` と記載していたが、実装は
``referenceWav / encoder`` だった。 ユーザは TypeError を踏むまで
気付けず、 docs と code の drift が CI 検出されなかった。

このスクリプトは README / docs の言語別 fenced code block (```python /
```javascript / ```rust / ```go / ```csharp) から関数呼び出し名を抽出し、
その識別子が対応する source tree (src/python_run/, src/wasm/, src/rust/
src/go/, src/csharp/) 内に export / pub / public で定義されているかを
grep ベースで検証する。

完全な型チェックや lint は本ツールのスコープ外。 「README に書かれた
公開 API 名が実装に存在するか」 という単一不変条件を保守的に守る。

検出対象:

  - ```python … piper.PiperVoice(...).method_name(...)
  - ```javascript … import { foo, bar } from '@piper-plus/g2p'
                    piper.synthesizeFromReferenceAudio(...)
  - ```rust       … piper_core::PiperVoice::method_name
  - ```go         … piperplus.MethodName
  - ```csharp     … PiperSession.MethodName

検出されたシンボル名が source tree に grep ヒットしなければ報告する。
偽陽性が出やすい (string literal / 内部関数名) ため、 デフォルトは
warning モード。 `--strict` で fail に昇格できる。

Exit codes:
    0  -- 全シンボルが source tree で見つかった (または warning モード)
    1  -- --strict 指定で未定義シンボル検出 / IO error

Usage:
    python scripts/check_readme_code_examples.py
    python scripts/check_readme_code_examples.py --strict
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent

LANG_TO_SOURCES: dict[str, list[str]] = {
    "python": ["src/python_run/piper/", "src/python/piper_train/"],
    "py": ["src/python_run/piper/", "src/python/piper_train/"],
    "javascript": ["src/wasm/openjtalk-web/src/", "src/wasm/g2p/src/"],
    "js": ["src/wasm/openjtalk-web/src/", "src/wasm/g2p/src/"],
    "typescript": ["src/wasm/openjtalk-web/src/", "src/wasm/g2p/src/"],
    "ts": ["src/wasm/openjtalk-web/src/", "src/wasm/g2p/src/"],
    "rust": ["src/rust/piper-core/src/", "src/rust/piper-cli/src/"],
    "rs": ["src/rust/piper-core/src/", "src/rust/piper-cli/src/"],
    "go": ["src/go/piperplus/", "src/go/cmd/piper-plus/"],
    "csharp": ["src/csharp/PiperPlus.Core/", "src/csharp/PiperPlus.Cli/"],
    "cs": ["src/csharp/PiperPlus.Core/", "src/csharp/PiperPlus.Cli/"],
}

# Symbols that show up in examples but are intentionally documented before
# being implemented, or which live in third-party packages.
ALLOWLIST: set[str] = {
    "print",
    "main",
    "println",
    "console",
    "log",
    "info",
    "warn",
    "error",
    "len",
    "range",
    "list",
    "dict",
    "str",
    "int",
    "float",
    "bool",
    "true",
    "false",
    "null",
    "None",
    "undefined",
    "Some",
    "Ok",
    "Err",
    "Result",
    "Option",
    "Vec",
    "String",
    "HashMap",
    "Box",
    "Arc",
    "Rc",
    "Default",
    "Debug",
    "Clone",
    "fmt",
    "fs",
    "io",
    "os",
    "path",
    "regex",
    "json",
    "tomllib",
    "pathlib",
    "Path",
    "open",
    "read",
    "write",
    "close",
    "fn",
    "let",
    "var",
    "const",
    "func",
    "def",
    "class",
    "struct",
    "enum",
    "import",
    "from",
    "use",
    "package",
    "namespace",
    "using",
    # Common stdlib / typing helpers that show up in cross-runtime examples.
    "Optional",
    "Union",
    "Any",
    "Iterator",
    "Iterable",
    "Sequence",
    "Mapping",
    "List",
    "Dict",
    "Tuple",
    "Set",
    "Type",
    "TypeVar",
    "Generic",
    "dataclass",
    "field",
    "subprocess",
    "asyncio",
    "logging",
    "argparse",
    "Callable",
    "Awaitable",
    "NoReturn",
    "Final",
    # JS / TS / Rust frequently seen names.
    "Promise",
    "async",
    "await",
    "yield",
    "return",
    "throw",
    "catch",
    "Self",
    "Future",
    "Stream",
    "Send",
    "Sync",
}

# Document tree roots to scan.
DOC_ROOTS = [
    "README.md",
    "src/python_run/README.md",
    "src/rust/README.md",
    "src/csharp/README.md",
    "src/go/README.md",
    "src/wasm/openjtalk-web/README.md",
    "src/wasm/g2p/README.md",
    "docs/features/",
    "docs/guides/",
]

# Matches fenced blocks: ```lang ... ```
CODE_BLOCK_RE = re.compile(
    r"^```(?P<lang>[a-zA-Z+-]+)\n(?P<body>.*?)^```",
    re.MULTILINE | re.DOTALL,
)

# Identifier-like tokens followed by ( or . — likely a function / method call.
CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*[\(\.]")


def find_doc_files() -> list[Path]:
    out: list[Path] = []
    for root_spec in DOC_ROOTS:
        path = REPO_ROOT / root_spec
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out.extend(p for p in path.rglob("*.md") if p.is_file())
    return out


def extract_calls(text: str) -> dict[str, set[str]]:
    """Return mapping language -> set of identifier tokens called in code blocks."""
    found: dict[str, set[str]] = defaultdict(set)
    for m in CODE_BLOCK_RE.finditer(text):
        lang = m.group("lang").lower()
        body = m.group("body")
        for cm in CALL_RE.finditer(body):
            ident = cm.group(1)
            if ident in ALLOWLIST:
                continue
            if ident.isupper():
                continue
            found[lang].add(ident)
    return found


def grep_sources(ident: str, source_dirs: list[str]) -> bool:
    """Return True if ``ident`` is defined anywhere under ``source_dirs``."""
    for src in source_dirs:
        full = REPO_ROOT / src
        if not full.exists():
            continue
        try:
            # `-F` fixed-string mode: identifier に regex metachar (e.g. `$`,
            # `.`, `*`) が含まれても literal で grep。 `-w` word boundary で
            # `synthesize` が `synthesizeFrom...` に余計に match するのを防ぐ。
            result = subprocess.run(
                ["git", "grep", "-l", "-F", "-w", "--", ident, "--", str(src)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="未定義シンボルを fail として扱う",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="チェックした全シンボルを出力",
    )
    args = parser.parse_args()

    doc_files = find_doc_files()
    if not doc_files:
        print("No README / docs found to validate", file=sys.stderr)
        return 0

    findings: list[tuple[Path, str, str]] = []
    total_symbols = 0

    for doc in doc_files:
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        per_lang = extract_calls(text)
        for lang, idents in per_lang.items():
            sources = LANG_TO_SOURCES.get(lang)
            if sources is None:
                continue
            for ident in sorted(idents):
                total_symbols += 1
                if not grep_sources(ident, sources):
                    findings.append((doc, lang, ident))

    if args.verbose:
        print(
            f"checked {total_symbols} unique symbol(s) across {len(doc_files)} doc file(s)",
            file=sys.stderr,
        )

    if findings:
        print(
            f"\n{len(findings)} doc code-example symbol(s) not found in source tree:",
            file=sys.stderr,
        )
        last_doc: Path | None = None
        for doc, lang, ident in findings:
            doc_rel = doc.relative_to(REPO_ROOT)
            if doc != last_doc:
                print(f"\n  {doc_rel}:", file=sys.stderr)
                last_doc = doc
            print(f"    [{lang}] {ident}", file=sys.stderr)
        print(
            "\nIf these are intentional (planned API / 3rd-party / typo-prone string),"
            " add them to ALLOWLIST in scripts/check_readme_code_examples.py.",
            file=sys.stderr,
        )
        if args.strict:
            return 1
        print(
            "\n(non-strict mode: warning only — re-run with --strict to fail)",
            file=sys.stderr,
        )
        return 0

    if args.verbose:
        print("OK: every doc code-example symbol resolves to a source tree match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
