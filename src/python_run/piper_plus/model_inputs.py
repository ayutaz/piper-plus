"""ONNX 入力名から、この runtime が組み立てられないモデルを読み込み時に拒否する。

参照条件付き (ref_spec_v1) モデルは参照音声の線形 magnitude spectrogram
``reference_spec`` [B, 513, T_ref] float32 と ``reference_spec_lengths`` [B]
int64 を必須入力に持つ。Python runtime (PiperVoice / piper_plus.api engine /
HTTP server) はこの入力を作らないため、warmup や合成で ORT の
"Required inputs missing" に落ちる (warmup はそれを warning にして握り潰す)
前に、何が足りないかを明示して止める。旧モデルの入力には一切触れない。

依存は標準ライブラリのみ (piper_plus.api.engine の no-piper_train 方針を守る)。
C++ runtime (src/cpp/piper.cpp:loadModel) も同じ入力名で拒否する。
"""

from __future__ import annotations

from collections.abc import Iterable
from os import PathLike


REFERENCE_SPEC_INPUT_NAMES: tuple[str, ...] = (
    "reference_spec",
    "reference_spec_lengths",
)


class UnsupportedModelInputError(RuntimeError):
    """モデルがこの runtime の組み立てられない入力を宣言している。"""


def reject_reference_spec_inputs(
    input_names: Iterable[str], model_path: str | PathLike[str]
) -> None:
    """``input_names`` に参照spec入力があれば :class:`UnsupportedModelInputError`。

    ``reference_spec`` / ``reference_spec_lengths`` のどちらか一方でも宣言して
    いれば拒否する (片方だけでも合成時に必須入力欠落になるため)。
    """
    names = set(input_names)
    found = [name for name in REFERENCE_SPEC_INPUT_NAMES if name in names]
    if not found:
        return
    raise UnsupportedModelInputError(
        f"Model {model_path} requires reference-spectrogram input "
        f"({', '.join(found)}; reference_conditioning schema ref_spec_v1), "
        "which this runtime does not support. Use a model exported without "
        "reference conditioning."
    )


def reject_unsupported_session_inputs(
    session: object, model_path: str | PathLike[str]
) -> None:
    """ORT session の宣言入力を検査する (:func:`reject_reference_spec_inputs`)。"""
    reject_reference_spec_inputs(
        (inp.name for inp in session.get_inputs()),  # type: ignore[attr-defined]
        model_path,
    )
