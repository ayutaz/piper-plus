"""Generate tiny diagnostic graphs; these are not speech/quality models.

Run with the repository's onnx dependency. IR/opset are deliberately old
enough for the minimum supported ORT Web. All speaker inputs affect output.
"""

import hashlib
import json
from pathlib import Path

import onnx
from onnx import TensorProto as T, helper as h


ROOT = Path(__file__).resolve().parent
CASES = [
    ("speaker-192-mask2", 192, 2),
    ("speaker-256-mask2", 256, 2),
    ("speaker-320-mask1", 320, 1),
    ("speaker-192-no-mask", 192, 0),
    ("speaker-dynamic-mask2", "embedding_dim", 2),
    ("no-speaker", None, 0),
]


def main():
    manifest = []
    for name, dim, rank in CASES:
        inputs = [
            h.make_tensor_value_info("input", T.INT64, ["batch", "phonemes"]),
            h.make_tensor_value_info("input_lengths", T.INT64, ["batch"]),
            h.make_tensor_value_info("scales", T.FLOAT, [3]),
            h.make_tensor_value_info("lid", T.INT64, ["batch"]),
        ]
        nodes = []
        if dim is not None:
            inputs.append(
                h.make_tensor_value_info("speaker_embedding", T.FLOAT, ["batch", dim])
            )
            nodes.append(
                h.make_node(
                    "ReduceMean", ["speaker_embedding"], ["embmean"], keepdims=0
                )
            )
            offset = "embmean"
            if rank:
                inputs.append(
                    h.make_tensor_value_info(
                        "speaker_embedding_mask",
                        T.INT64,
                        ["batch"] if rank == 1 else ["batch", 1],
                    )
                )
                nodes.extend(
                    [
                        h.make_node(
                            "Cast",
                            ["speaker_embedding_mask"],
                            ["maskfloat"],
                            to=T.FLOAT,
                        ),
                        h.make_node(
                            "ReduceMean", ["maskfloat"], ["maskmean"], keepdims=0
                        ),
                        h.make_node("Mul", ["embmean", "maskmean"], ["offset"]),
                    ]
                )
                offset = "offset"
            nodes.append(h.make_node("Add", [offset, "base"], ["output"]))
        else:
            nodes.append(h.make_node("Identity", ["base"], ["output"]))
        graph = h.make_graph(
            nodes,
            name,
            inputs,
            [h.make_tensor_value_info("output", T.FLOAT, [1, 1, 16])],
            [h.make_tensor("base", T.FLOAT, [1, 1, 16], [0.25] * 16)],
        )
        model = h.make_model(
            graph, opset_imports=[h.make_opsetid("", 13)], ir_version=9
        )
        onnx.checker.check_model(model)
        data = model.SerializeToString()
        (ROOT / f"{name}.onnx").write_bytes(data)
        manifest.append(
            {
                "file": f"{name}.onnx",
                "dimension": dim,
                "maskRank": rank,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
