"""Download model files from Hugging Face Hub or create dummy models"""

import json
from pathlib import Path

import onnx
from onnx import TensorProto, helper


def create_dummy_onnx_model(output_path: Path, num_symbols: int = 130):
    """Create a minimal dummy ONNX model for testing"""

    # Define input tensors
    input_ids = helper.make_tensor_value_info(
        "input", TensorProto.INT64, [1, None]
    )
    input_lengths = helper.make_tensor_value_info(
        "input_lengths", TensorProto.INT64, [1]
    )
    scales = helper.make_tensor_value_info(
        "scales", TensorProto.FLOAT, [3]
    )

    # Define output tensor
    output = helper.make_tensor_value_info(
        "output", TensorProto.FLOAT, [1, 1, None]
    )

    # Create a simple identity-like operation
    # This is just a placeholder - real model would have complex operations
    identity_node = helper.make_node(
        "Identity",
        inputs=["input"],
        outputs=["identity_out"],
        name="identity"
    )

    # Create a constant output shape
    shape_const = helper.make_tensor(
        "shape_const",
        TensorProto.INT64,
        dims=[3],
        vals=[1, 1, 22050]  # 1 second at 22050 Hz
    )

    # Create a constant fill node
    const_fill = helper.make_node(
        "ConstantOfShape",
        inputs=["shape_const"],
        outputs=["output"],
        name="const_fill"
    )

    # Create the graph
    graph = helper.make_graph(
        [identity_node, const_fill],
        "dummy_tts_model",
        [input_ids, input_lengths, scales],
        [output],
        [shape_const]
    )

    # Create the model
    model = helper.make_model(graph)

    # Save the model
    onnx.save(model, str(output_path))
    print(f"Created dummy model: {output_path}")


def create_dummy_config(output_path: Path, language: str = "en"):
    """Create a dummy model configuration"""
    config = {
        "audio": {
            "sample_rate": 22050
        },
        "espeak": {
            "voice": "en-us" if language == "en" else "ja"
        },
        "language": {
            "code": language
        },
        "inference": {
            "noise_scale": 0.667,
            "length_scale": 1,
            "noise_w": 0.8
        },
        "phoneme_type": "espeak" if language == "en" else "openjtalk",
        "phoneme_map": {},
        "phoneme_id_map": {
            "_": [0], "^": [1], "$": [2], " ": [3],
            "a": [4], "b": [5], "c": [6], "d": [7], "e": [8]
        },
        "num_symbols": 10,
        "num_speakers": 1,
        "speaker_id_map": {}
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Created config: {output_path}")


def download_models():
    """Create dummy models for demo purposes"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)

    # Create dummy models
    models = [
        ("ja_JP-test-medium.onnx", "ja", "Japanese medium quality model"),
        ("test_voice.onnx", "en", "English test model"),
    ]

    print("Creating dummy models for demo...")
    for filename, lang, description in models:
        onnx_path = models_dir / filename
        json_path = models_dir / f"{filename}.json"

        if not onnx_path.exists():
            print(f"Creating {description}...")
            create_dummy_onnx_model(onnx_path)

        if not json_path.exists():
            create_dummy_config(json_path, language=lang)

    print("Model setup complete!")


if __name__ == "__main__":
    download_models()
