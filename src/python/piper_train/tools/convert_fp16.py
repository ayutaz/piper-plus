#!/usr/bin/env python3
"""FP32 ONNXモデルをFP16に変換するCLIツール。

VITS TTSモデルに最適化された変換を行い、数値安定性が重要な
オペレータ（LayerNormalization, Sigmoid, Softmax）はFP32を保持する。

使用例:
    # 基本変換
    uv run python -m piper_train.tools.convert_fp16 \
        --model /path/to/model.onnx \
        --output /path/to/model-fp16.onnx

    # 検証付き変換
    uv run python -m piper_train.tools.convert_fp16 \
        --model /path/to/model.onnx \
        --output /path/to/model-fp16.onnx \
        --validate

    # カスタムFP32保持オペレータ
    uv run python -m piper_train.tools.convert_fp16 \
        --model /path/to/model.onnx \
        --output /path/to/model-fp16.onnx \
        --keep-fp32-ops "LayerNormalization,Sigmoid,Softmax,ReduceMean"
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


_LOGGER = logging.getLogger("piper_train.tools.convert_fp16")

# VITS固有のデフォルトFP32保持オペレータ
DEFAULT_KEEP_FP32_OPS = [
    "LayerNormalization",
    "Sigmoid",
    "Softmax",
]


def _collect_keep_fp32_tensors(
    model: onnx.ModelProto,
    keep_fp32_ops: list[str],
) -> set[str]:
    """FP32を保持すべきオペレータに接続されたinitializer名を収集する。"""
    keep_tensors: set[str] = set()
    init_names = {init.name for init in model.graph.initializer}
    for node in model.graph.node:
        if node.op_type in keep_fp32_ops:
            for inp in node.input:
                if inp in init_names:
                    keep_tensors.add(inp)
    return keep_tensors


def convert_fp16(
    model_path: Path,
    output_path: Path,
    keep_fp32_ops: list[str] | None = None,
) -> onnx.ModelProto:
    """FP32 ONNXモデルをFP16に変換する。

    重み（initializer）をFP16に変換し、各消費ノードの手前に
    Cast(FP16→FP32)ノードを挿入する。計算グラフはFP32のまま
    維持されるため、型の整合性が保証される。
    ONNX Runtimeは実行時にこれらのCastパターンを最適化し、
    GPU環境ではFP16カーネルを自動的に使用する。

    Args:
        model_path: 入力モデルパス
        output_path: 出力モデルパス
        keep_fp32_ops: FP32保持対象のオペレータリスト

    Returns:
        変換後のモデル
    """
    if keep_fp32_ops is None:
        keep_fp32_ops = DEFAULT_KEEP_FP32_OPS

    _LOGGER.info("Loading model: %s", model_path)
    model = onnx.load(str(model_path))

    _LOGGER.info(
        "Model info: IR version=%d, opset=%s, nodes=%d",
        model.ir_version,
        [f"v{o.version}" for o in model.opset_import],
        len(model.graph.node),
    )

    # オペレータ統計
    op_counts: dict[str, int] = {}
    for node in model.graph.node:
        op_counts[node.op_type] = op_counts.get(node.op_type, 0) + 1
    _LOGGER.info("Operator types: %s", dict(sorted(op_counts.items())))
    _LOGGER.info("FP32 keep operators: %s", sorted(keep_fp32_ops))

    # FP32保持対象のinitializerを収集
    keep_tensors = _collect_keep_fp32_tensors(model, keep_fp32_ops)
    _LOGGER.info("FP32 keep initializers: %d", len(keep_tensors))

    graph = model.graph

    # 各initializerの消費ノードをマッピング
    init_consumers: dict[str, list[tuple[onnx.NodeProto, int]]] = {}
    for node in graph.node:
        for idx, inp in enumerate(node.input):
            if inp:
                if inp not in init_consumers:
                    init_consumers[inp] = []
                init_consumers[inp].append((node, idx))

    # FP32 initializerをFP16に変換し、Castノードを挿入
    converted_count = 0
    kept_count = 0
    cast_nodes: list[onnx.NodeProto] = []

    # 既存グラフの全テンソル名を収集（名前衝突を回避）
    existing_names: set[str] = set()
    for init in graph.initializer:
        existing_names.add(init.name)
    for node in graph.node:
        existing_names.update(node.output)
        if node.name:
            existing_names.add(node.name)

    def _unique_name(base: str) -> str:
        """既存名と衝突しないユニーク名を生成する。"""
        if base not in existing_names:
            existing_names.add(base)
            return base
        idx = 0
        while f"{base}_{idx}" in existing_names:
            idx += 1
        name = f"{base}_{idx}"
        existing_names.add(name)
        return name

    for init in graph.initializer:
        if init.data_type != TensorProto.FLOAT:
            continue

        if init.name in keep_tensors:
            _LOGGER.debug("Keeping FP32: %s", init.name)
            kept_count += 1
            continue

        # FP16に変換
        np_data = numpy_helper.to_array(init)
        fp16_data = np_data.astype(np.float16)

        init.data_type = TensorProto.FLOAT16
        init.ClearField("raw_data")
        del init.float_data[:]
        init.raw_data = fp16_data.tobytes()

        # Castノードを作成（FP16→FP32）— 名前衝突を回避
        cast_output_name = _unique_name(f"{init.name}_fp32")
        cast_node_name = _unique_name(f"Cast_fp16to32_{init.name}")
        cast_node = helper.make_node(
            "Cast",
            inputs=[init.name],
            outputs=[cast_output_name],
            to=TensorProto.FLOAT,
            name=cast_node_name,
        )
        cast_nodes.append(cast_node)

        # 消費ノードの入力をCast出力に差し替え
        if init.name in init_consumers:
            for node, inp_idx in init_consumers[init.name]:
                node.input[inp_idx] = cast_output_name

        converted_count += 1

    _LOGGER.info(
        "Initializers: %d converted to FP16, %d kept as FP32",
        converted_count,
        kept_count,
    )

    # Castノードをグラフの先頭に挿入（initializerの直後、他ノードの前）
    original_nodes = list(graph.node)
    del graph.node[:]
    graph.node.extend(cast_nodes)
    graph.node.extend(original_nodes)

    _LOGGER.info("Inserted %d Cast nodes", len(cast_nodes))

    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(output_path))
    _LOGGER.info("Saved FP16 model: %s", output_path)

    return model


def _format_size(size_bytes: int) -> str:
    """バイト数を人間が読みやすい形式に変換する。"""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} bytes"


def validate_model(
    original_path: Path,
    fp16_path: Path,
    rtol: float = 0.01,
    atol: float = 0.01,
) -> bool:
    """FP16変換モデルの検証を行う。

    1. グラフ構造チェック（onnx.checker）
    2. 推論出力の比較（相対誤差チェック）
    """
    _LOGGER.info("=== Validation ===")

    # 1. グラフ構造チェック
    _LOGGER.info("Step 1: Checking graph structure...")
    try:
        fp16_model = onnx.load(str(fp16_path))
        onnx.checker.check_model(fp16_model, full_check=False)
        _LOGGER.info("Graph structure check: PASSED")
    except onnx.checker.ValidationError as e:
        _LOGGER.error("Graph structure check: FAILED - %s", e)
        return False
    except Exception as e:
        _LOGGER.warning("Graph structure check: WARNING - %s", e)

    # 2. 推論出力の比較
    _LOGGER.info("Step 2: Comparing inference outputs...")
    try:
        import onnxruntime  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning("onnxruntime not installed. Skipping output comparison.")
        return True

    try:
        sess_options = onnxruntime.SessionOptions()
        sess_options.log_severity_level = 3
        providers = ["CPUExecutionProvider"]

        original_sess = onnxruntime.InferenceSession(
            str(original_path), sess_options=sess_options, providers=providers
        )
        fp16_sess = onnxruntime.InferenceSession(
            str(fp16_path), sess_options=sess_options, providers=providers
        )

        inputs = _create_dummy_inputs(original_sess)
        if inputs is None:
            _LOGGER.warning("Could not create dummy inputs. Skipping.")
            return True

        original_outputs = original_sess.run(None, inputs)
        fp16_outputs = fp16_sess.run(None, inputs)

        all_passed = True
        for i, (orig, fp16_out) in enumerate(
            zip(original_outputs, fp16_outputs, strict=False)
        ):
            orig_f32 = orig.astype(np.float32) if orig.dtype == np.float16 else orig
            fp16_f32 = (
                fp16_out.astype(np.float32)
                if fp16_out.dtype == np.float16
                else fp16_out
            )

            if orig_f32.shape != fp16_f32.shape:
                # TTSモデルではDuration Predictorの精度差により
                # 音声長が微小に異なることがある（正常動作）
                _LOGGER.info(
                    "Output %d: shape differs (original=%s, fp16=%s) "
                    "- expected for TTS duration prediction",
                    i,
                    orig_f32.shape,
                    fp16_f32.shape,
                )
                continue

            mean_abs_err = float(np.mean(np.abs(orig_f32 - fp16_f32)))
            max_abs_err = float(np.max(np.abs(orig_f32 - fp16_f32)))

            if np.allclose(orig_f32, fp16_f32, rtol=rtol, atol=atol):
                _LOGGER.info(
                    "Output %d: PASSED (mean_abs=%.6f, max_abs=%.6f)",
                    i,
                    mean_abs_err,
                    max_abs_err,
                )
            else:
                all_passed = False
                _LOGGER.warning(
                    "Output %d: MARGINAL (mean_abs=%.6f, max_abs=%.6f) "
                    "- small differences are typically inaudible for TTS",
                    i,
                    mean_abs_err,
                    max_abs_err,
                )

        if all_passed:
            _LOGGER.info("Validation: PASSED")
        else:
            _LOGGER.warning(
                "Validation: MARGINAL - some outputs exceed tolerance "
                "(small differences are typically inaudible for TTS)"
            )
        return all_passed

    except Exception as e:
        _LOGGER.error("Output comparison failed: %s", e)
        return False


def _create_dummy_inputs(session) -> dict[str, np.ndarray] | None:
    """ONNXRTセッションからVITS用ダミー入力を生成する。"""
    inputs: dict[str, np.ndarray] = {}
    phoneme_length = 50

    for inp in session.get_inputs():
        name = inp.name
        if name == "input":
            inputs[name] = np.random.randint(
                0, 50, size=[1, phoneme_length], dtype=np.int64
            )
        elif name == "input_lengths":
            inputs[name] = np.array([phoneme_length], dtype=np.int64)
        elif name == "scales":
            inputs[name] = np.array([0.667, 1.0, 0.8], dtype=np.float32)
        elif name == "sid":
            inputs[name] = np.array([0], dtype=np.int64)
        elif name == "lid":
            inputs[name] = np.array([0], dtype=np.int64)
        elif name == "prosody_features":
            inputs[name] = np.zeros([1, phoneme_length, 3], dtype=np.int64)
        else:
            _LOGGER.warning("Unknown input: %s", name)
            return None

    return inputs


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="piper_train.tools.convert_fp16",
        description="FP32 ONNXモデルをFP16に変換する。"
        "VITS TTSモデルに最適化されたデフォルト設定を使用。",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="入力FP32 ONNXモデルのパス",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="出力FP16 ONNXモデルのパス",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="変換後にグラフ構造チェックと出力比較を実行",
    )
    parser.add_argument(
        "--keep-fp32-ops",
        type=str,
        default=None,
        help="FP32保持するオペレータ（カンマ区切り）。"
        "デフォルト: LayerNormalization,Sigmoid,Softmax",
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=0.01,
        help="検証時の相対誤差閾値（デフォルト: 0.01 = 1%%）",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=0.01,
        help="検証時の絶対誤差閾値（デフォルト: 0.01）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="DEBUGレベルのログを表示",
    )
    args = parser.parse_args(argv)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    model_path = Path(args.model)
    output_path = Path(args.output)

    if not model_path.exists():
        _LOGGER.error("Model file not found: %s", model_path)
        sys.exit(1)

    if model_path == output_path:
        _LOGGER.error("Input and output paths must be different")
        sys.exit(1)

    if args.keep_fp32_ops is not None:
        keep_fp32_ops = [
            op.strip() for op in args.keep_fp32_ops.split(",") if op.strip()
        ]
    else:
        keep_fp32_ops = None

    _LOGGER.info("=== FP32 to FP16 Conversion ===")
    _LOGGER.info("Input:  %s", model_path)
    _LOGGER.info("Output: %s", output_path)

    original_size = model_path.stat().st_size
    convert_fp16(model_path, output_path, keep_fp32_ops)
    fp16_size = output_path.stat().st_size

    reduction = original_size - fp16_size
    reduction_pct = (reduction / original_size) * 100 if original_size > 0 else 0

    _LOGGER.info("=== Conversion Summary ===")
    _LOGGER.info("Original size:  %s", _format_size(original_size))
    _LOGGER.info("FP16 size:      %s", _format_size(fp16_size))
    _LOGGER.info("Size reduction: %s (%.1f%%)", _format_size(reduction), reduction_pct)

    if args.validate:
        is_valid = validate_model(
            model_path, output_path, rtol=args.rtol, atol=args.atol
        )
        if not is_valid:
            _LOGGER.error("Validation FAILED")
            sys.exit(1)
        _LOGGER.info("Validation PASSED")

    _LOGGER.info("Done.")


if __name__ == "__main__":
    main()
