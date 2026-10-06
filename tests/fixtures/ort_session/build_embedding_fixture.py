"""Build tiny ONNX graphs that enforce declared speaker embedding dimensions."""

from pathlib import Path

import onnx
from onnx import TensorProto, helper


def build(dimension: int, masked: bool) -> None:
    inputs = [
        helper.make_tensor_value_info("input", TensorProto.INT64, [1, "length"]),
        helper.make_tensor_value_info("input_lengths", TensorProto.INT64, [1]),
        helper.make_tensor_value_info("scales", TensorProto.FLOAT, [3]),
        helper.make_tensor_value_info("speaker_embedding", TensorProto.FLOAT, [1, dimension]),
    ]
    initializers = [
        helper.make_tensor("axes", TensorProto.INT64, [1], [2]),
        helper.make_tensor("wave", TensorProto.FLOAT, [1, 1, 512], [0.5, -0.5] * 256),
    ]
    nodes = [
        helper.make_node("ReduceMean", ["speaker_embedding"], ["mean"], axes=[1], keepdims=1),
        helper.make_node("Unsqueeze", ["mean", "axes"], ["embedding_audio"]),
        helper.make_node("Add", ["wave", "embedding_audio"], ["unmasked"]),
    ]
    if masked:
        inputs.append(helper.make_tensor_value_info("speaker_embedding_mask", TensorProto.INT64, [1, 1]))
        initializers.append(helper.make_tensor("zero", TensorProto.FLOAT, [], [0.0]))
        nodes.extend([
            helper.make_node("Cast", ["speaker_embedding_mask"], ["mask_float"], to=TensorProto.FLOAT),
            helper.make_node("Mul", ["mask_float", "zero"], ["mask_zero"]),
            helper.make_node("Unsqueeze", ["mask_zero", "axes"], ["mask_audio"]),
            helper.make_node("Add", ["unmasked", "mask_audio"], ["output"]),
        ])
    else:
        nodes.append(helper.make_node("Identity", ["unmasked"], ["output"]))
    graph = helper.make_graph(nodes, "embedding-dimension", inputs, [
        helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1, 512])
    ], initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=8)
    onnx.checker.check_model(model)
    destination = Path(__file__).parent / f"embedding_{dimension}_{'masked' if masked else 'legacy'}.onnx"
    onnx.save(model, destination)
    print(destination)


if __name__ == "__main__":
    for dimension in (192, 256):
        for masked in (False, True):
            build(dimension, masked)
