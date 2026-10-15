"""Tiny duration-capable graph for CLI output tests, not a speech-quality model."""

import json
import sys
from pathlib import Path

import onnx
from onnx import TensorProto as T, helper


def build(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    inputs = [
        helper.make_tensor_value_info("input", T.INT64, [1, "phonemes"]),
        helper.make_tensor_value_info("input_lengths", T.INT64, [1]),
        helper.make_tensor_value_info("scales", T.FLOAT, [3]),
    ]
    nodes = [
        helper.make_node("Shape", ["input"], ["shape"]),
        helper.make_node(
            "ConstantOfShape",
            ["shape"],
            ["durations"],
            value=helper.make_tensor("duration", T.FLOAT, [1], [1]),
        ),
        helper.make_node(
            "Constant",
            [],
            ["output"],
            value=helper.make_tensor("audio", T.FLOAT, [1, 1, 16000], [0.1] * 16000),
        ),
    ]
    graph = helper.make_graph(
        nodes,
        "cli-consumer-fixture",
        inputs,
        [
            helper.make_tensor_value_info("output", T.FLOAT, [1, 1, 16000]),
            helper.make_tensor_value_info("durations", T.FLOAT, [1, "phonemes"]),
        ],
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 15)], ir_version=8
    )
    onnx.checker.check_model(model, full_check=True)
    onnx.save(model, directory / "model.onnx")
    config = {
        "audio": {"sample_rate": 16000, "hop_size": 256},
        "inference": {"noise_scale": 0, "length_scale": 1, "noise_w": 0},
        "phoneme_type": "multilingual",
        "phoneme_id_map": {"_": [0], "^": [1], "$": [2], "a": [10], "b": [11]},
        "num_symbols": 12,
        "num_speakers": 1,
        "language": {"code": "es"},
        "language_id_map": {"es": 0},
    }
    (directory / "model.onnx.json").write_text(json.dumps(config), encoding="utf-8")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
