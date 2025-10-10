"""ONNX-based prediction for "何" (nani/nan) reading disambiguation.

This module uses lightweight ONNX models to predict whether "何" should
be read as "ナニ" (nani) or "ナン" (nan) based on context.

Original source: kabosu-core (https://github.com/q9uri/kabosu-core)
License: MIT (see COPYING file)
"""

from pathlib import Path
from typing import Union

import numpy as np

from ..types import NjdObject


X_COLS = ["pos", "pos_group1", "pos_group2", "pron", "ctype", "cform"]
MODEL_DIR = Path(__file__).parent

# ONNX モデルをロード
# 非常に軽量なモデルのため、import 時に ONNX モデルをロードするオーバーヘッドはほとんどない
try:
    from onnxruntime import InferenceSession

    enc_session = InferenceSession(
        MODEL_DIR / "nani_enc.onnx",
        providers=["CPUExecutionProvider"],
    )
    model_session = InferenceSession(
        MODEL_DIR / "nani_model.onnx",
        providers=["CPUExecutionProvider"],
    )
except ImportError:
    # ONNX Runtime がインストールされていない場合は、モデルをロードしない
    # ONNX Runtime は onnxruntime (無印, CPU 版)・onnxruntime-gpu (CUDA 版)・onnxruntime-directml (DirectML 版) などが提供されている
    # ユーザーはこのうちいずれかのパッケージ「のみ」をインストールする必要があるため、ライブラリ側からは依存関係を明示できない
    print("Warning: ONNX Runtime is not installed. Nani prediction will be disabled.")
    print("Please install ONNX Runtime by `pip install onnxruntime`")
    enc_session = None
    model_session = None


def predict(input_njd: list[Union[NjdObject, None]]) -> int:
    """Predict whether "何" should be read as "ナニ" (0) or "ナン" (1).

    Args:
        input_njd: List of NJD feature objects representing context.
                   Can contain None values which are filtered out.

    Returns:
        0 for "ナニ" (nani), 1 for "ナン" (nan)
        Returns 0 (nani) if ONNX Runtime is not available.
    """
    # ONNX Runtime がインストールされていない場合は常に 0 を返す
    if enc_session is None or model_session is None:
        return 0

    if input_njd == [None]:
        return 0
    else:
        # 入力データを準備
        input_data = np.array(
            [[njd[col] for col in X_COLS] for njd in input_njd if njd is not None]
        )

        # OneHotEncoder で変換
        enc_input = {"input": input_data}
        enc_output = enc_session.run(None, enc_input)

        # RandomForestClassifier で予測
        model_input = {"input": enc_output[0].astype(np.float32)}
        model_output = model_session.run(None, model_input)

        return int(model_output[0][0])
