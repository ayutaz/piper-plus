"""参照spec入力の有無だけが違う tiny ONNX graph を生成する (音声品質モデルではない)。

用途: 未対応 runtime (Python runtime / C++) が ``reference_spec`` /
``reference_spec_lengths`` 入力を宣言したモデルを読み込み時に明示拒否し、
旧モデル (legacy) は従来どおり読み込めることを、実際の ORT session で確かめる。

- C++: ``src/cpp/tests/test_reference_spec_rejection.cpp``
- Python: ``src/python_run/tests/test_reference_schema_rejection.py``
  (生成済みファイルが本 script の出力と一致することも同 test で検査する)

全入力が出力に寄与する (ORT が未使用入力を落とさないことに依存しない)。
出力は ``output[0, 0, t] = input[0, t] * 0.001`` + (他入力の総和 × 0)。
IR/opset は最低対応 ORT (1.22) でも読める値に固定する。

再生成: ``uv run python src/cpp/tests/fixtures/reference_spec_inputs/generate.py``
"""

from __future__ import annotations

import json
from pathlib import Path

import onnx
from onnx import TensorProto as T, helper as h


ROOT = Path(__file__).resolve().parent

# 旧 export (export_onnx.py) の入力。legacy_full は現行 zero-shot export
# (zs-v1 と同じ並び: speaker_embedding -> lid -> prosody_features) を写す。
_BASE_INPUTS = [
    ("input", T.INT64, ["batch", "phonemes"]),
    ("input_lengths", T.INT64, ["batch"]),
    ("scales", T.FLOAT, [3]),
]
_LEGACY_OPTIONAL_INPUTS = [
    ("speaker_embedding", T.FLOAT, ["batch", 192]),
    ("lid", T.INT64, ["batch"]),
    ("prosody_features", T.INT64, ["batch", "phonemes", 3]),
]
# ref_spec_v1 schema (interface contract) の追加入力。
_REFERENCE_SPEC = ("reference_spec", T.FLOAT, ["batch", 513, "ref_frames"])
_REFERENCE_SPEC_LENGTHS = ("reference_spec_lengths", T.INT64, ["batch"])

CASES: dict[str, list[tuple[str, int, list]]] = {
    "legacy_minimal": list(_BASE_INPUTS),
    "legacy_full": _BASE_INPUTS + _LEGACY_OPTIONAL_INPUTS,
    "ref_spec": _BASE_INPUTS
    + _LEGACY_OPTIONAL_INPUTS
    + [_REFERENCE_SPEC, _REFERENCE_SPEC_LENGTHS],
    "ref_spec_without_lengths": _BASE_INPUTS
    + _LEGACY_OPTIONAL_INPUTS
    + [_REFERENCE_SPEC],
    "ref_spec_lengths_only": _BASE_INPUTS
    + _LEGACY_OPTIONAL_INPUTS
    + [_REFERENCE_SPEC_LENGTHS],
}

# phoneme_id_map の key は C++ が 1 codepoint を要求する。
CONFIG = {
    "audio": {"sample_rate": 22050},
    "phoneme_type": "multilingual",
    "num_symbols": 50,
    "num_speakers": 1,
    "num_languages": 1,
    "language_id_map": {"ja": 0},
    "phoneme_id_map": {
        "_": [0],
        "^": [1],
        "$": [2],
        **{chr(0x61 + i): [4 + i] for i in range(26)},
    },
    "inference": {"noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8},
}

# output = input * WAVE_GAIN。test 側の期待値計算と共有する。
WAVE_GAIN = 0.001


def build_model(name: str) -> onnx.ModelProto:
    specs = CASES[name]
    inputs = [h.make_tensor_value_info(n, dtype, shape) for n, dtype, shape in specs]
    initializers = [
        h.make_tensor("gain", T.FLOAT, [], [WAVE_GAIN]),
        h.make_tensor("zero", T.FLOAT, [], [0.0]),
        h.make_tensor("channel_axis", T.INT64, [1], [1]),
    ]
    nodes = [
        h.make_node("Cast", ["input"], ["input_f"], to=T.FLOAT),
        h.make_node("Mul", ["input_f", "gain"], ["wave_2d"]),
        h.make_node("Unsqueeze", ["wave_2d", "channel_axis"], ["wave"]),
    ]
    current = "wave"
    for input_name, dtype, _shape in specs:
        if input_name == "input":
            continue
        source = input_name
        if dtype != T.FLOAT:
            source = f"{input_name}_f"
            nodes.append(h.make_node("Cast", [input_name], [source], to=T.FLOAT))
        nodes.extend(
            [
                h.make_node("ReduceSum", [source], [f"{input_name}_sum"], keepdims=0),
                h.make_node(
                    "Mul", [f"{input_name}_sum", "zero"], [f"{input_name}_zero"]
                ),
                h.make_node(
                    "Add", [current, f"{input_name}_zero"], [f"{input_name}_acc"]
                ),
            ]
        )
        current = f"{input_name}_acc"
    nodes.append(h.make_node("Identity", [current], ["output"]))
    graph = h.make_graph(
        nodes,
        name,
        inputs,
        [h.make_tensor_value_info("output", T.FLOAT, ["batch", 1, "phonemes"])],
        initializers,
    )
    model = h.make_model(graph, opset_imports=[h.make_opsetid("", 13)], ir_version=8)
    onnx.checker.check_model(model)
    return model


def config_text() -> str:
    return json.dumps(CONFIG, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    for name in CASES:
        onnx.save(build_model(name), ROOT / f"{name}.onnx")
    # write_bytes: Windows でも LF のまま書く (drift test は文字列一致で比較する)。
    (ROOT / "config.json").write_bytes(config_text().encode("utf-8"))


if __name__ == "__main__":
    main()
