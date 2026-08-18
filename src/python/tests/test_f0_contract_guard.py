"""S-2 の契約ガード: F0 経路が評価器を目的関数化していないことの構造的固定。

docs/spec/zs-eval-contract.md §2 禁止事項 4 /
docs/design/zero-shot-v10b-s2-f0-design.md §5.3-5.4。

S-2 は契約の**明示された例外**の上に乗っている: 「GT frame-level F0 を教師と
する per-frame 回帰」は評価器を一切消費しないので許される。しかし例外の境界は
狭く、以下を作った瞬間に §4.3 の F0 gate が検出器として死ぬ:

1. **生成波形から F0 を推定して GT と比べる loss** (推定器が微分可能かに依らず)
2. **F0 / エネルギーの分布モーメント** (std / p5-95 レンジ / skew / kurt) を
   目的化する項
3. 学習コードからの評価メトリクス module の import (E-8 gate が機械的に block)

このファイルは 1 と 2 を「構造的にできない状態」に固定する。中心的な不変条件は
**学習パッケージ (``piper_train/vits/**``) が F0 推定器を一切持たない**こと —
生成音声の F0 を測るには推定器が要るので、推定器が無ければ禁止事項 1 は書けない。

過去の事故: SCL が CAM++ を目的関数化した結果、CAM++ が改善検出器として死に、
same-utt SECS 0.775 を誤報した (docs/design/zero-shot-speaker-similarity-
root-cause.md)。同じ轍を F0 で踏まないための予防線。
"""

from __future__ import annotations

import inspect
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
VITS_DIR = REPO_ROOT / "src" / "python" / "piper_train" / "vits"
MAIN_PY = REPO_ROOT / "src" / "python" / "piper_train" / "__main__.py"


def _training_sources() -> list[Path]:
    return sorted(VITS_DIR.rglob("*.py")) + [MAIN_PY]


# --------------------------------------------------------------------------
# 禁止事項 1: 生成音声から F0 を推定する経路が存在しない
# --------------------------------------------------------------------------


# 学習コードに現れてはいけない F0 推定の入口。
#
# ``librosa`` / ``torchaudio`` 自体は mel / resample で正当に使われているので
# module 名では禁止できない。F0 を出す **API 名**を直接禁止する (これが
# 「生成波形の F0 を測る」ために必ず通る門)。
_BANNED_F0_ESTIMATORS = {
    "pyworld": re.compile(r"\bpyworld\b|\bimport\s+pyworld\b"),
    "librosa.pyin": re.compile(r"\bpyin\s*\("),
    "librosa.yin": re.compile(r"\blibrosa\.yin\b|\byin\s*\("),
    "torchaudio pitch": re.compile(r"\bdetect_pitch_frequency\b"),
    "crepe": re.compile(r"\b(?:torchcrepe|crepe)\b"),
    "piptrack": re.compile(r"\bpiptrack\b"),
}


@pytest.mark.parametrize("estimator", sorted(_BANNED_F0_ESTIMATORS))
def test_training_package_contains_no_f0_estimator(estimator):
    """学習コードは F0 推定 API を持たない = 生成音声の F0 を測れない。

    S-2 の学習側は ``tools/extract_f0.py`` が作った ``.npy`` を読むだけ。
    ここに推定器が入ってきたら「生成波形の F0 を GT と比べる」loss が
    書けるようになり、契約 §2 の例外境界を越える。
    """
    pattern = _BANNED_F0_ESTIMATORS[estimator]
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _training_sources()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{estimator} appears in training code: {offenders}. "
        "F0 estimation belongs in tools/extract_f0.py (offline preprocessing)."
    )


def test_f0_loss_signature_takes_no_generated_audio():
    """``f0_prediction_loss`` は波形を受け取らない (構造的に禁止事項 1 が不可能)。"""
    from piper_train.vits.losses import f0_prediction_loss

    params = list(inspect.signature(f0_prediction_loss).parameters)
    assert params == ["logf0_pred", "vuv_logit", "f0_gt", "vuv_gt", "frame_mask"]
    for name in params:
        assert "wav" not in name and "audio" not in name and "y_hat" not in name


def test_f0_loss_source_contains_no_distribution_moments():
    """禁止事項 2: loss 本体が std / percentile / skew / kurtosis を使わない。"""
    from piper_train.vits import losses

    source = inspect.getsource(losses.f0_prediction_loss)
    # docstring には「禁止する形」の説明として単語が出るので本体だけを見る
    body = source.split('"""')[-1]
    for banned in (".std(", "percentile", "quantile", "skew", "kurtosis", ".var("):
        assert banned not in body, f"{banned} must not appear in f0_prediction_loss"


def test_f0_loss_ignores_everything_except_gt_and_prediction():
    """入力 5 つ以外に依存しない = グローバル状態から統計を引いてこない。"""
    torch = pytest.importorskip("torch")
    from piper_train.vits.losses import f0_prediction_loss

    args = (
        torch.full((2, 1, 8), 5.3),
        torch.zeros(2, 1, 8),
        torch.full((2, 1, 8), 200.0),
        torch.ones(2, 1, 8),
        torch.ones(2, 1, 8),
    )
    a = [float(v) for v in f0_prediction_loss(*args)]
    b = [float(v) for v in f0_prediction_loss(*args)]
    assert a == b


# --------------------------------------------------------------------------
# 禁止事項 3: E-8 隔離 gate (train → metric import) が通る
# --------------------------------------------------------------------------


def test_zs_metric_isolation_gate_still_passes():
    """S-2 の追加後も学習 ↔ 評価メトリクスの import 隔離が保たれている。"""
    script = REPO_ROOT / "scripts" / "check_zs_metric_isolation.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_extract_f0_is_outside_the_isolation_gate_scope():
    """``tools/extract_f0.py`` は「オフライン前処理」として gate の対象外。

    対象内 (role="train") に分類されると、前処理が torch を import している
    だけで fail する。契約 §2 の例外境界と一致していることを固定する。
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import importlib

        gate = importlib.import_module("check_zs_metric_isolation")
    finally:
        sys.path.pop(0)

    assert gate.classify_role("src/python/piper_train/tools/extract_f0.py") is None
    assert gate.classify_role("src/python/piper_train/vits/models.py") == "train"


# --------------------------------------------------------------------------
# R6: 学習ターゲットと評価の推定器が分離されている
# --------------------------------------------------------------------------


def test_training_target_and_eval_use_different_f0_estimators():
    """学習ターゲット = pyworld、評価 = librosa.pyin の分離を固定する。

    同一推定器だと「その推定器が高分散と読む音」を作る方向の抜け道が開き、
    §4.3 の F0 gate が独立性を失う (設計 doc R6)。
    """
    target_src = (
        REPO_ROOT / "src/python/piper_train/tools/extract_f0.py"
    ).read_text(encoding="utf-8")
    eval_src = (
        REPO_ROOT / "src/python/piper_train/tools/acoustic_frames.py"
    ).read_text(encoding="utf-8")

    assert "pyworld" in target_src
    assert "pyworld" not in eval_src
    assert "pyin" in eval_src
    # 学習ターゲット側は評価器を **import しない** (docstring での言及は
    # 分離の意図を明示するために必要なので、import 文だけを見る)
    assert not re.search(r"^\s*(?:import|from)\s+librosa\b", target_src, re.MULTILINE)
