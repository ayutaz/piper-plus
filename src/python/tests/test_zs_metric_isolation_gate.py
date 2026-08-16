"""Tests for scripts/check_zs_metric_isolation.py (E-8 学習↔評価 隔離 gate).

教訓① (評価器の目的化 = 検出器の喪失) の機械的強制を pin する
(docs/design/zero-shot-v10b-quality-plan.md §2 E-8 / phase_a_spec.md §5.3):

- Rule A (学習→評価): 学習コード (piper_train/vits/** + piper_train/__main__.py)
  から評価メトリクスモジュール (measure_band_noise / measure_comb_artifacts /
  measure_prosody / acoustic_frames / eval_zs_secs) の import を禁止。
- Rule B (評価→学習): メトリクスモジュール自身の torch / piper_train.vits
  import を禁止 (微分可能化の入口を構造的に閉じる。onnxruntime は勾配なしの
  推論のみなので許可)。
- tools/ 配下のオフライン前処理 (データゲート) は禁止対象外
  (docs/spec/zs-eval-contract.md §2 禁止事項 4 の例外境界と一致)。

gate script は classify_role / scan_text の純関数を module-level に持つ契約
(pytest から importlib で直接テスト可能にするため)。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = REPO_ROOT / "scripts" / "check_zs_metric_isolation.py"

METRIC_MODULE_RELPATHS = (
    "src/python/piper_train/tools/measure_band_noise.py",
    "src/python/piper_train/tools/measure_comb_artifacts.py",
    "src/python/piper_train/tools/measure_prosody.py",
    "src/python/piper_train/tools/acoustic_frames.py",
    "src/python/piper_train/tools/eval_zs_secs.py",
)


@pytest.fixture(scope="module")
def gate():
    """gate script を module として load する。

    module 名は非汎用 (script-dir import shadowing の既知事故回避 —
    memory/python_script_dir_import_shadowing.md)。
    """
    if not GATE_PATH.is_file():
        pytest.fail(
            f"gate script が未実装: {GATE_PATH} "
            "(Phase A E-8、phase_a_spec.md §5.3 — TDD red)"
        )
    spec = importlib.util.spec_from_file_location(
        "zs_metric_isolation_gate_module", GATE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load {GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestClassifyRole:
    def test_train_scope(self, gate):
        assert gate.classify_role("src/python/piper_train/vits/lightning.py") == "train"
        assert gate.classify_role("src/python/piper_train/vits/models.py") == "train"
        assert gate.classify_role("src/python/piper_train/__main__.py") == "train"

    def test_metric_scope(self, gate):
        # acoustic_frames (共有 helper) も ban list に含む — 迂回 import の穴を塞ぐ
        for rel in METRIC_MODULE_RELPATHS:
            assert gate.classify_role(rel) == "metric", rel

    def test_offline_data_gate_scripts_out_of_scope(self, gate):
        """オフライン前処理 (データゲート) は流用禁止の対象外 (契約 §2-4 例外)。"""
        assert (
            gate.classify_role(
                "src/python/piper_train/tools/prepare_multilingual_dataset.py"
            )
            is None
        )
        assert gate.classify_role("src/python/piper_train/export_onnx.py") is None
        # テストコードはメトリクスを自由に import できる
        assert gate.classify_role("src/python/tests/test_eval_zs_secs.py") is None


@pytest.mark.unit
class TestScanTrainScope:
    """Rule A: 学習 scope でのメトリクス import 検出 (fixture テキストで検証)。"""

    def test_absolute_import_flagged(self, gate):
        text = "from piper_train.tools.measure_prosody import prosody_stats\n"
        assert gate.scan_text("train", text)

    def test_import_module_form_flagged(self, gate):
        assert gate.scan_text("train", "import piper_train.tools.eval_zs_secs\n")

    def test_from_tools_import_metric_flagged(self, gate):
        assert gate.scan_text(
            "train", "from piper_train.tools import measure_band_noise\n"
        )

    def test_relative_import_flagged(self, gate):
        assert gate.scan_text(
            "train",
            "from ..tools.measure_band_noise import voiced_high_band_excess\n",
        )
        assert gate.scan_text("train", "from ..tools import measure_comb_artifacts\n")

    def test_single_dot_relative_import_flagged(self, gate):
        """単一ドット相対 (__main__.py の house style) も検出 (review 指摘)。

        __main__.py の既存 import は全て単一ドット相対 (from .vits.lightning
        等) — 学習エントリポイントへの最も自然な綴りが gate の死角だった。
        """
        assert gate.scan_text(
            "train", "from .tools.measure_prosody import prosody_stats\n"
        )
        assert gate.scan_text("train", "from .tools import measure_prosody\n")

    def test_paren_multiline_import_flagged(self, gate):
        """括弧複数行 import (ruff format 生成形式) は開き括弧行で flag。"""
        assert gate.scan_text(
            "train", "from piper_train.tools import (\n    measure_prosody,\n)\n"
        )
        assert gate.scan_text(
            "train", "from ..tools import (\n    measure_band_noise,\n)\n"
        )
        assert gate.scan_text(
            "train", "from .tools import (\n    measure_comb_artifacts,\n)\n"
        )

    def test_paren_open_flagged_even_without_metric_name(self, gate):
        """開き括弧行は継続行の内容に関わらず保守的に flag (構造限界の保守側
        倒し — 継続行のメトリクス名は行単位 regex で追えない)。train scope の
        tools 列挙 import は稀なので false positive 許容。緩める場合は継続行
        追跡の実装 + 本テストの同時更新が必要 (黙った弱体化の防止)。"""
        violations = gate.scan_text(
            "train",
            "from piper_train.tools import (\n    prepare_multilingual_dataset,\n)\n",
        )
        assert violations
        assert violations[0][0] == 1  # 開き括弧行 (line 1) が報告される

    def test_importlib_string_literal_flagged(self, gate):
        """importlib.import_module / __import__ の文字列リテラル経由も flag。"""
        assert gate.scan_text(
            "train",
            "importlib.import_module('piper_train.tools.measure_prosody')\n",
        )
        assert gate.scan_text("train", '__import__("piper_train.tools.eval_zs_secs")\n')

    def test_tools_nonmetric_import_allowed(self, gate):
        """tools 内の非メトリクスモジュール import は許可 (前処理チェーン)。"""
        assert (
            gate.scan_text(
                "train", "from piper_train.tools import prepare_multilingual_dataset\n"
            )
            == []
        )
        assert (
            gate.scan_text(
                "train", "from ..tools import prepare_multilingual_dataset\n"
            )
            == []
        )
        # 単一ドット相対の非メトリクス import も許可 (export_onnx の house style)
        assert (
            gate.scan_text("train", "from .tools import prepare_multilingual_dataset\n")
            == []
        )
        assert (
            gate.scan_text("train", "from .tools.convert_fp16 import convert_fp16\n")
            == []
        )
        # 非メトリクスの importlib も許可
        assert (
            gate.scan_text(
                "train", "importlib.import_module('piper_train.vits.lightning')\n"
            )
            == []
        )

    def test_line_numbers_reported(self, gate):
        text = "import os\nfrom piper_train.tools.measure_prosody import x\n"
        violations = gate.scan_text("train", text)
        assert len(violations) == 1
        assert violations[0][0] == 2  # (line_no, line, rule)


@pytest.mark.unit
class TestScanMetricScope:
    """Rule B: メトリクスモジュール内の torch / vits import 検出。"""

    def test_torch_import_flagged(self, gate):
        assert gate.scan_text("metric", "import torch\n")
        assert gate.scan_text("metric", "from torch import nn\n")

    def test_vits_import_flagged(self, gate):
        assert gate.scan_text("metric", "from piper_train.vits import models\n")
        assert gate.scan_text("metric", "import piper_train.vits.models\n")

    def test_paren_multiline_import_flagged(self, gate):
        """括弧複数行 import は開き括弧行で flag (Rule A と同方針)。"""
        assert gate.scan_text("metric", "from torch import (\n    nn,\n)\n")
        assert gate.scan_text(
            "metric", "from piper_train.vits import (\n    models,\n)\n"
        )
        assert gate.scan_text("metric", "from piper_train import (\n    vits,\n)\n")
        assert gate.scan_text("metric", "from .. import (\n    vits,\n)\n")

    def test_relative_parent_import_flagged(self, gate):
        """from .. import vits (親 package 経由の迂回) も flag。"""
        assert gate.scan_text("metric", "from .. import vits\n")

    def test_importlib_string_literal_flagged(self, gate):
        assert gate.scan_text("metric", "importlib.import_module('torch')\n")
        assert gate.scan_text("metric", "importlib.import_module('torch.nn')\n")
        assert gate.scan_text("metric", "__import__('piper_train.vits.models')\n")

    def test_analysis_deps_allowed(self, gate):
        assert gate.scan_text("metric", "import numpy as np\n") == []
        assert gate.scan_text("metric", "import librosa\n") == []
        # onnxruntime は勾配なしの推論のみ (eval_zs_secs で使用) — 許可
        assert gate.scan_text("metric", "import onnxruntime\n") == []

    def test_metric_house_style_tools_imports_allowed(self, gate):
        """eval_zs_secs 自身の house style — piper_train.tools からの括弧 import
        (兄弟メトリクス / 共有 helper) は metric scope では正当なので許可。"""
        assert (
            gate.scan_text(
                "metric",
                "from piper_train.tools import (\n    measure_band_noise,\n)\n",
            )
            == []
        )
        assert (
            gate.scan_text(
                "metric",
                "from piper_train.tools.acoustic_frames import (\n"
                "    FrameAnalysis,\n"
                ")\n",
            )
            == []
        )
        assert gate.scan_text("metric", "from .acoustic_frames import load_wav\n") == []


@pytest.mark.unit
def test_full_repo_clean():
    """引数なし実行 = full-repo sweep が exit 0 (現 repo が clean であること)。"""
    if not GATE_PATH.is_file():
        pytest.fail(
            f"gate script が未実装: {GATE_PATH} "
            "(Phase A E-8、phase_a_spec.md §5.3 — TDD red)"
        )
    proc = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
