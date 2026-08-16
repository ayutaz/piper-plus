#!/usr/bin/env python3
"""zero-shot 評価メトリクスと学習コードの import 隔離 gate (Phase A E-8)。

教訓① (評価器の目的化 = 検出器の喪失) の機械的強制。SCL が CAM++ を目的関数化
した結果、CAM++ が改善検出器として死んだ (same-utt SECS 0.775 誤報 / Phase 0
Arm B の片側上昇 — docs/design/zero-shot-warm-restart-diagnostics-phase0-1.md、
frozen encoder 崩壊は v10a-r2 §10)。同じ事故を評価メトリクス (帯域 / コム /
韻律統計) で繰り返さないため、契約 docs/spec/zs-eval-contract.md §2 禁止事項 4
(学習流用の恒久禁止) を regex で強制する。

Rule A (学習 → 評価の方向、E-8 本体):
    学習コード (``src/python/piper_train/vits/**`` + ``piper_train/__main__.py``)
    からメトリクスモジュール (measure_band_noise / measure_comb_artifacts /
    measure_prosody / acoustic_frames / eval_zs_secs) を import したら fail。
    共有 helper の acoustic_frames も ban list に含む (迂回 import の穴を塞ぐ)。
    tools/ 配下のオフライン前処理 (データゲート、例: prepare_multilingual_dataset)
    は対象外 — 契約 §2 禁止事項 4 の例外境界 (オフライン前処理のデータゲートは
    流用禁止の対象外) と一致する。

Rule B (評価 → 学習の方向、微分不能の構造化):
    メトリクスモジュール自身が torch または piper_train.vits を import したら
    fail。「微分可能化が容易」な韻律統計 (plan E-8) を構造的に微分不能にする。
    onnxruntime は勾配なしの推論のみなので許可 (eval_zs_secs の encoder 推論)。

検出する import 形式 (Rule A/B 共通の方針):
    - 単一行の絶対 / 相対 import。相対は単一ドット (``from .tools`` —
      __main__.py の house style) と 2 ドット (``from ..tools`` — vits/ 配下)
      の両方 (``\\.{1,2}``)。
    - 括弧複数行 import (ruff format が長い import に生成する形式) は行単位
      regex では継続行を見られないため、**開き括弧行そのものを保守的に flag**
      (``from ...tools import (`` / ``from piper_train import (``)。scope 内で
      正当な列挙 import は稀なので false positive は許容 — 単一行に書き換えるか
      ALLOWLIST + コードレビューで解消する。
    - ``importlib.import_module("...") / __import__("...")`` の文字列リテラル
      経由。変数経由の動的 import は regex では検出不能 (構造限界) —
      そこまでの迂回は「偶発ドリフト」ではなく意図的回避であり、コードレビュー
      と契約 (docs/spec/zs-eval-contract.md §2 禁止事項 4) が受け持つ。

実装は scripts/check_no_legacy_piper_imports.py と同型 (行 regex +
git ls-files fallback + ALLOWLIST 空 + argv でファイル指定可)。純関数
``classify_role`` / ``scan_text`` は tests/test_zs_metric_isolation_gate.py が
importlib で直接テストする契約。

Exit codes:
    0  -- 隔離が保たれている
    1  -- 違反あり (file:line を stderr に出力)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


# Local import: shared UTF-8 stdout/stderr reconfiguration for Windows consoles.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from platform_utils import force_utf8_output  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent

# 評価メトリクスモジュール (ban list)。eval_zs_secs と共有 helper の
# acoustic_frames も含む — 迂回 import の穴を塞ぐ【仕様 D17】。
METRIC_MODULES: tuple[str, ...] = (
    "measure_band_noise",
    "measure_comb_artifacts",
    "measure_prosody",
    "acoustic_frames",
    "eval_zs_secs",
)

_METRIC_ALT = "|".join(METRIC_MODULES)

# Rule A: 学習 scope でのメトリクス import 検出 regex 群。
# 相対形は「METRIC 名を含む場合のみ」fail — tools 内の非メトリクスモジュール
# (オフライン前処理) の import は許可する。相対形は単一ドット (`from .tools`、
# __main__.py の house style) と 2 ドット (`from ..tools`、vits/ 配下) の両方を
# 対象にする (`\.{1,2}`)。
#
# 括弧複数行 import (`from ...tools import (\n    ...,\n)` — ruff format が長い
# import に生成する形式) は行単位 regex では継続行のメトリクス名を見られない
# ため、**開き括弧行そのものを保守的に flag** する。train scope で tools からの
# 列挙 import はメトリクス以外でも稀なので false positive は許容 (必要なら
# 単一行 import に書き換えるか ALLOWLIST + コードレビュー)。
_TRAIN_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(rf"^\s*(?:from|import)\s+piper_train\.tools\.(?:{_METRIC_ALT})\b"),
        "train-imports-metric (absolute)",
    ),
    (
        re.compile(
            rf"^\s*from\s+piper_train\.tools\s+import\s+.*\b(?:{_METRIC_ALT})\b"
        ),
        "train-imports-metric (from tools)",
    ),
    (
        re.compile(rf"^\s*from\s+\.{{1,2}}tools\.(?:{_METRIC_ALT})\s+import\b"),
        "train-imports-metric (relative)",
    ),
    (
        re.compile(rf"^\s*from\s+\.{{1,2}}tools\s+import\s+.*\b(?:{_METRIC_ALT})\b"),
        "train-imports-metric (relative from tools)",
    ),
    (
        re.compile(r"^\s*from\s+(?:piper_train\.tools|\.{1,2}tools)\s+import\s*\("),
        "train-imports-metric (paren import from tools — conservatively flagged)",
    ),
    (
        re.compile(
            rf"(?:\bimport_module|\b__import__)\s*\(.*[\"'](?:[\w.]+\.)?"
            rf"(?:{_METRIC_ALT})\b"
        ),
        "train-imports-metric (importlib)",
    ),
)

# Rule B: メトリクスモジュール内の torch / piper_train.vits import 検出。
# import 文にアンカーする (docstring/コメントの言及は false-positive にしない)。
# Rule A 同様、括弧複数行 import は開き括弧行を保守的に flag し
# (`from piper_train import (` / `from .. import (` — メトリクスが親 package
# から列挙 import する正当な理由はない)、importlib の文字列リテラル経由も塞ぐ。
_METRIC_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^\s*(?:import|from)\s+torch\b"),
        "metric-imports-torch",
    ),
    (
        re.compile(r"^\s*(?:import|from)\s+piper_train\.vits\b"),
        "metric-imports-vits",
    ),
    (
        re.compile(r"^\s*from\s+piper_train\s+import\s+.*\bvits\b"),
        "metric-imports-vits (from piper_train)",
    ),
    (
        re.compile(r"^\s*from\s+\.\.\s+import\s+.*\bvits\b"),
        "metric-imports-vits (relative from piper_train)",
    ),
    (
        re.compile(r"^\s*from\s+\.\.vits\b"),
        "metric-imports-vits (relative)",
    ),
    (
        re.compile(r"^\s*from\s+(?:piper_train|\.\.)\s+import\s*\("),
        "metric-imports-vits (paren import from piper_train — conservatively flagged)",
    ),
    (
        re.compile(
            r"(?:\bimport_module|\b__import__)\s*\(.*[\"']"
            r"(?:torch\b|piper_train\.vits\b)"
        ),
        "metric-imports-torch/vits (importlib)",
    ),
)

_METRIC_PATHS = frozenset(
    f"src/python/piper_train/tools/{name}.py" for name in METRIC_MODULES
)

# 意図的な例外 (追加にはコードレビュー必須)。導入時点で空。
ALLOWLIST: frozenset[str] = frozenset()


def classify_role(rel_posix: str) -> str | None:
    """repo 相対 POSIX パス → "train" / "metric" / None (scope 外)。

    - "train": piper_train/vits/**/*.py + piper_train/__main__.py
    - "metric": METRIC_MODULES の 5 ファイル
    - None: それ以外 (tools/ のオフライン前処理・テスト・export 等 —
      契約 §2 禁止事項 4 の例外境界【仕様 D18】)
    """
    if rel_posix in _METRIC_PATHS:
        return "metric"
    if rel_posix == "src/python/piper_train/__main__.py":
        return "train"
    if rel_posix.startswith("src/python/piper_train/vits/") and rel_posix.endswith(
        ".py"
    ):
        return "train"
    return None


def scan_text(role: str, text: str) -> list[tuple[int, str, str]]:
    """role ("train" / "metric") のファイル内容を走査し違反行を返す純関数。

    Returns:
        list of (line_no, line, rule_name)。違反なしなら []。
    """
    rules = {"train": _TRAIN_RULES, "metric": _METRIC_RULES}.get(role)
    if not rules:
        return []
    violations: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern, rule_name in rules:
            if pattern.search(line):
                violations.append((line_no, line.rstrip(), rule_name))
                break
    return violations


def _iter_repo_python_files() -> list[Path]:
    """tracked *.py を git ls-files で列挙 (非 git checkout は rglob fallback)。"""
    try:
        tracked = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", errors="replace")
        return [REPO_ROOT / p for p in tracked.split("\0") if p and p.endswith(".py")]
    except (OSError, subprocess.CalledProcessError):
        ignore_dirs = {
            "build",
            ".venv",
            "venv",
            "node_modules",
            "target",
            "dist",
            ".git",
            "__pycache__",
            ".mypy_cache",
        }
        return [
            p
            for p in REPO_ROOT.rglob("*.py")
            if p.is_file()
            and not ignore_dirs.intersection(p.relative_to(REPO_ROOT).parts)
        ]


def main(argv: list[str]) -> int:
    force_utf8_output()

    paths = [Path(p) for p in argv] if argv else _iter_repo_python_files()

    failures: list[tuple[str, int, str, str]] = []
    scanned = 0
    for path in paths:
        if not path.is_file() or path.suffix != ".py":
            continue
        try:
            rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        if rel in ALLOWLIST:
            continue
        role = classify_role(rel)
        if role is None:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line, rule_name in scan_text(role, text):
            failures.append((rel, line_no, line, rule_name))

    if not failures:
        print(
            f"OK: scanned {scanned} in-scope file(s); zero-shot eval metrics "
            f"remain isolated from training code (Rule A: train→metric import, "
            f"Rule B: metric→torch/vits import)."
        )
        return 0

    print(
        f"ERROR: {len(failures)} zs-metric isolation violation(s) found:",
        file=sys.stderr,
    )
    for rel, line_no, line, rule_name in failures:
        print(f"  {rel}:{line_no}: [{rule_name}] {line}", file=sys.stderr)
    print(
        "\nWhy this fails: 評価メトリクス (band / comb / prosody / SECS) を学習"
        " loss / reward に流用すると、評価器そのものが最適化対象になり改善検出器"
        "として死ぬ (SCL が CAM++ を目的化して same-utt SECS 0.775 を誤報した"
        "事故と同型 — frozen encoder 崩壊は v10a-r2 の §10)。torch import の禁止"
        "は「微分可能化が容易」なメトリクスを構造的に微分不能へ倒すため。",
        file=sys.stderr,
    )
    print(
        "\n契約: docs/spec/zs-eval-contract.md §2 禁止事項 4-5 / §4。"
        "オフライン前処理のデータゲート (prepare_* 等) は対象外。"
        "GT を教師とする回帰 loss (mel / STFT / MRD / S-2 pitch predictor) も"
        "対象外 — 禁止は「評価器の目的関数化」のみ。",
        file=sys.stderr,
    )
    print(
        "\n意図的な例外が必要な場合は scripts/check_zs_metric_isolation.py の "
        "ALLOWLIST に理由コメント付きで追加し、コードレビューを受けること。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
