"""Tests for ONNX Runtime session utilities (ort_utils.py).

Verifies that create_session_options() produces settings aligned with
the C#/Rust engine implementations and that get_providers() returns
the correct execution providers for each device type.
"""

import logging
import multiprocessing
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import onnxruntime
import pytest

from piper_train.ort_utils import (
    _build_cache_paths,
    _get_device_label,
    _get_logical_core_count,
    create_session_options,
    create_session_with_cache,
    get_providers,
    warmup_onnx_session,
)


@pytest.mark.unit
class TestCreateSessionOptions:
    """create_session_options() の設定値テスト."""

    def test_graph_optimization_level(self):
        opts = create_session_options()
        assert (
            opts.graph_optimization_level
            == onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )

    def test_execution_mode_sequential(self):
        opts = create_session_options()
        assert opts.execution_mode == onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    def test_inter_op_threads_is_one(self):
        opts = create_session_options()
        assert opts.inter_op_num_threads == 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=128)
    def test_intra_op_threads_capped_at_max(self, _mock):
        """128 コア環境: intra_op は上限 4 を超えない."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 4

    def test_intra_op_threads_at_least_one(self):
        opts = create_session_options()
        assert opts.intra_op_num_threads >= 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=16)
    def test_intra_op_threads_16_cores(self, _mock):
        """16 コア環境: min(16 // 2, 4) = 4."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 4

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=8)
    def test_intra_op_threads_8_cores(self, _mock):
        """8 コア環境: min(8 // 2, 4) = 4 — 上限に到達."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 4

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=4)
    def test_intra_op_threads_4_cores(self, _mock):
        """4 コア環境: min(4 // 2, 4) = 2."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 2

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=3)
    def test_intra_op_threads_3_cores(self, _mock):
        """3 コア (奇数): min(3 // 2, 4) = 1."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=2)
    def test_intra_op_threads_2_cores(self, _mock):
        """2 コア環境: min(2 // 2, 4) = min(1, 4) = 1."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 1

    @patch("piper_train.ort_utils._get_logical_core_count", return_value=1)
    def test_intra_op_threads_1_core(self, _mock):
        """Docker --cpus=1: 1 // 2 = 0 → 0 or 1 = 1."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 1

    def test_memory_arena_enabled(self):
        opts = create_session_options()
        assert opts.enable_cpu_mem_arena is True

    def test_memory_pattern_enabled(self):
        opts = create_session_options()
        assert opts.enable_mem_pattern is True

    def test_memory_reuse_enabled(self):
        opts = create_session_options()
        assert opts.enable_mem_reuse is True

    def test_returns_session_options_instance(self):
        opts = create_session_options()
        assert isinstance(opts, onnxruntime.SessionOptions)

    def test_dynamic_block_base(self):
        opts = create_session_options()
        assert opts.get_session_config_entry("session.dynamic_block_base") == "4"

    def test_returns_new_instance_each_call(self):
        """毎回新しい SessionOptions オブジェクトを返す."""
        opts_a = create_session_options()
        opts_b = create_session_options()
        assert opts_a is not opts_b


@pytest.mark.unit
class TestCreateSessionOptionsParams:
    """create_session_options() の引数テスト."""

    def test_intra_op_threads_override_1(self):
        """intra_op_threads=1 が反映される."""
        opts = create_session_options(intra_op_threads=1)
        assert opts.intra_op_num_threads == 1

    def test_intra_op_threads_override_2(self):
        """intra_op_threads=2 が反映される."""
        opts = create_session_options(intra_op_threads=2)
        assert opts.intra_op_num_threads == 2

    def test_inter_op_threads_override(self):
        """inter_op_threads=2 が反映される."""
        opts = create_session_options(inter_op_threads=2)
        assert opts.inter_op_num_threads == 2


@pytest.mark.unit
class TestPiperIntraThreadsEnv:
    """PIPER_INTRA_THREADS 環境変数オーバーライドのテスト."""

    @patch.dict("os.environ", {"PIPER_INTRA_THREADS": "2"})
    def test_env_overrides_auto_detection(self):
        """環境変数が自動検出より優先される."""
        opts = create_session_options()
        assert opts.intra_op_num_threads == 2

    @patch.dict("os.environ", {"PIPER_INTRA_THREADS": "3"})
    def test_env_overrides_explicit_arg(self):
        """環境変数が引数 intra_op_threads より優先される."""
        opts = create_session_options(intra_op_threads=1)
        assert opts.intra_op_num_threads == 3

    @patch.dict("os.environ", {"PIPER_INTRA_THREADS": "not_a_number"})
    def test_env_invalid_value_falls_through(self):
        """不正な PIPER_INTRA_THREADS は無視され自動検出にフォールバック."""
        opts = create_session_options()
        assert opts.intra_op_num_threads >= 1


@pytest.mark.unit
class TestGetLogicalCoreCount:
    """_get_logical_core_count() のテスト."""

    @patch("os.sched_getaffinity", create=True, return_value={0, 1, 2, 3})
    def test_uses_sched_getaffinity(self, _mock):
        """sched_getaffinity が利用可能ならその結果を返す."""
        assert _get_logical_core_count() == 4

    @patch("os.sched_getaffinity", create=True, side_effect=AttributeError)
    @patch("os.cpu_count", return_value=8)
    def test_fallback_to_cpu_count(self, _mock_cpu, _mock_affinity):
        """sched_getaffinity が AttributeError → os.cpu_count() にフォールバック."""
        assert _get_logical_core_count() == 8

    @patch("os.sched_getaffinity", create=True, side_effect=AttributeError)
    @patch("os.cpu_count", return_value=None)
    def test_fallback_to_default_when_cpu_count_none(self, _mock_cpu, _mock_affinity):
        """os.cpu_count() が None → デフォルト 2."""
        assert _get_logical_core_count() == 2


@pytest.mark.unit
class TestGetProviders:
    """get_providers() のデバイス別テスト."""

    def test_cpu_provider(self):
        providers = get_providers("cpu")
        assert providers == ["CPUExecutionProvider"]

    @patch(
        "piper_train.ort_utils.onnxruntime.get_available_providers",
        return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    def test_gpu_provider_with_cuda(self, _mock):
        providers = get_providers("gpu")
        assert "CUDAExecutionProvider" in providers
        assert "CPUExecutionProvider" in providers

    @patch(
        "piper_train.ort_utils.onnxruntime.get_available_providers",
        return_value=["CPUExecutionProvider"],
    )
    def test_gpu_provider_no_cuda_fallback(self, _mock):
        providers = get_providers("gpu")
        assert providers == ["CPUExecutionProvider"]

    @patch(
        "piper_train.ort_utils.onnxruntime.get_available_providers",
        return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    def test_auto_provider_with_cuda(self, _mock):
        providers = get_providers("auto")
        assert "CUDAExecutionProvider" in providers

    @patch(
        "piper_train.ort_utils.onnxruntime.get_available_providers",
        return_value=["CPUExecutionProvider"],
    )
    def test_auto_provider_no_cuda(self, _mock):
        providers = get_providers("auto")
        assert providers == ["CPUExecutionProvider"]

    def test_default_is_cpu(self):
        providers = get_providers()
        assert providers == ["CPUExecutionProvider"]


# ---------------------------------------------------------------------------
# Warmup tests
# ---------------------------------------------------------------------------


def _make_mock_session(
    *,
    has_sid=False,
    has_lid=False,
    has_prosody=False,
    has_speaker_embedding=False,
    speaker_embedding_dim=256,
):
    """Create a mock InferenceSession with configurable optional inputs."""
    session = MagicMock(spec=onnxruntime.InferenceSession)

    # Build input list
    inputs = []
    for name in ("input", "input_lengths", "scales"):
        inp = MagicMock()
        inp.name = name
        inputs.append(inp)
    if has_sid:
        inp = MagicMock()
        inp.name = "sid"
        inputs.append(inp)
    if has_lid:
        inp = MagicMock()
        inp.name = "lid"
        inputs.append(inp)
    if has_prosody:
        inp = MagicMock()
        inp.name = "prosody_features"
        inputs.append(inp)
    if has_speaker_embedding:
        inp = MagicMock()
        inp.name = "speaker_embedding"
        inp.shape = ["batch_size", speaker_embedding_dim]
        inputs.append(inp)
        inp = MagicMock()
        inp.name = "speaker_embedding_mask"
        inp.shape = ["batch_size", 1]
        inputs.append(inp)

    session.get_inputs.return_value = inputs

    # Single output
    out = MagicMock()
    out.name = "output"
    session.get_outputs.return_value = [out]

    return session


@pytest.mark.unit
class TestWarmup:
    """warmup_onnx_session() のテスト."""

    def test_warmup_completes_successfully(self):
        """session.run が DEFAULT_WARMUP_RUNS 回呼ばれる."""
        session = _make_mock_session()
        warmup_onnx_session(session)
        assert session.run.call_count == 2

    def test_warmup_failure_is_non_fatal(self, caplog):
        """RuntimeError が発生しても warning ログのみで例外を再送しない."""
        session = _make_mock_session()
        session.run.side_effect = RuntimeError("test error")
        with caplog.at_level(logging.WARNING):
            warmup_onnx_session(session)
        assert "Warmup failed (non-fatal)" in caplog.text

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "1"})
    def test_disable_warmup_env_1(self):
        """PIPER_DISABLE_WARMUP=1 でスキップ."""
        session = _make_mock_session()
        warmup_onnx_session(session)
        session.run.assert_not_called()

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "true"})
    def test_disable_warmup_env_true(self):
        """PIPER_DISABLE_WARMUP=true でスキップ."""
        session = _make_mock_session()
        warmup_onnx_session(session)
        session.run.assert_not_called()

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "yes"})
    def test_disable_warmup_env_yes(self):
        """PIPER_DISABLE_WARMUP=yes でスキップ."""
        session = _make_mock_session()
        warmup_onnx_session(session)
        session.run.assert_not_called()

    def test_runs_zero_returns_immediately(self):
        """runs=0 なら即 return."""
        session = _make_mock_session()
        warmup_onnx_session(session, runs=0)
        session.run.assert_not_called()

    def test_optional_inputs_sid_only(self):
        """sid のみの場合、inputs に sid が含まれる."""
        session = _make_mock_session(has_sid=True)
        warmup_onnx_session(session)
        call_args = session.run.call_args
        inputs = call_args[0][1]
        assert "sid" in inputs
        assert "lid" not in inputs
        assert "prosody_features" not in inputs

    def test_optional_inputs_all(self):
        """sid, lid, prosody_features 全てある場合."""
        session = _make_mock_session(has_sid=True, has_lid=True, has_prosody=True)
        warmup_onnx_session(session)
        call_args = session.run.call_args
        inputs = call_args[0][1]
        assert "sid" in inputs
        assert "lid" in inputs
        assert "prosody_features" in inputs

    def test_optional_inputs_none(self):
        """オプション入力が一切ない場合."""
        session = _make_mock_session()
        warmup_onnx_session(session)
        call_args = session.run.call_args
        inputs = call_args[0][1]
        assert "sid" not in inputs
        assert "lid" not in inputs
        assert "prosody_features" not in inputs

    def test_dummy_input_shape_and_values(self):
        """phoneme_ids の shape=(1,100), BOS=1, EOS=2, 中間=8."""
        session = _make_mock_session()
        warmup_onnx_session(session)
        call_args = session.run.call_args
        inputs = call_args[0][1]
        phoneme_ids = inputs["input"]
        assert phoneme_ids.shape == (1, 100)
        assert phoneme_ids[0, 0] == 1  # BOS
        assert phoneme_ids[0, -1] == 2  # EOS
        assert phoneme_ids[0, 1] == 8  # dummy fill

    def test_prosody_features_shape(self):
        """prosody_features の shape=(1,100,3), dtype=int64."""
        session = _make_mock_session(has_prosody=True)
        warmup_onnx_session(session)
        call_args = session.run.call_args
        inputs = call_args[0][1]
        prosody = inputs["prosody_features"]
        assert prosody.shape == (1, 100, 3)
        assert prosody.dtype == np.int64

    def test_optional_inputs_speaker_embedding(self):
        """speaker_embedding 入力がある場合、zeros + mask=0 が渡される (issue #385)."""
        session = _make_mock_session(
            has_speaker_embedding=True, speaker_embedding_dim=192
        )
        warmup_onnx_session(session)
        inputs = session.run.call_args[0][1]
        assert "speaker_embedding" in inputs
        assert "speaker_embedding_mask" in inputs
        assert inputs["speaker_embedding"].shape == (1, 192)
        assert inputs["speaker_embedding"].dtype == np.float32
        assert np.all(inputs["speaker_embedding"] == 0.0)
        assert inputs["speaker_embedding_mask"].tolist() == [[0]]
        assert inputs["speaker_embedding_mask"].dtype == np.int64

    def test_warmup_with_speaker_embedding_no_mask(self):
        """Zero-shot exports omit speaker_embedding_mask — warmup must skip it.

        Regression guard for Issue #527 fix (commit 5188b088): warmup
        previously fed speaker_embedding_mask unconditionally, which raised
        InvalidArgument on zero-shot ONNX models (v7 / Tsukuyomi FT) that
        declare only speaker_embedding as input.
        """
        # Build a session that declares speaker_embedding but NOT the mask.
        session = MagicMock(spec=onnxruntime.InferenceSession)
        inputs = []
        for name in ("input", "input_lengths", "scales"):
            inp = MagicMock()
            inp.name = name
            inputs.append(inp)
        emb_inp = MagicMock()
        emb_inp.name = "speaker_embedding"
        emb_inp.shape = ["batch_size", 192]
        inputs.append(emb_inp)
        session.get_inputs.return_value = inputs
        out = MagicMock()
        out.name = "output"
        session.get_outputs.return_value = [out]

        warmup_onnx_session(session)

        feeds = session.run.call_args[0][1]
        assert "speaker_embedding" in feeds
        assert "speaker_embedding_mask" not in feeds, (
            "warmup must not feed speaker_embedding_mask when the session "
            "does not declare it (zero-shot export compatibility, Issue #527)"
        )
        assert feeds["speaker_embedding"].shape == (1, 192)
        assert feeds["speaker_embedding"].dtype == np.float32

    def test_warmup_with_speaker_embedding_and_mask(self):
        """Backward compat: legacy models declaring both inputs still get both."""
        session = _make_mock_session(
            has_speaker_embedding=True, speaker_embedding_dim=256
        )
        warmup_onnx_session(session)

        feeds = session.run.call_args[0][1]
        assert "speaker_embedding" in feeds
        assert "speaker_embedding_mask" in feeds
        assert feeds["speaker_embedding"].shape == (1, 256)
        assert feeds["speaker_embedding"].dtype == np.float32
        assert feeds["speaker_embedding_mask"].shape == (1, 1)
        assert feeds["speaker_embedding_mask"].dtype == np.int64

    def test_speaker_embedding_symbolic_shape_uses_default_dim(self):
        """ONNX 入力 shape が symbolic の場合、デフォルト 256 次元を使う."""
        session = _make_mock_session(has_speaker_embedding=True)
        for inp in session.get_inputs.return_value:
            if inp.name == "speaker_embedding":
                inp.shape = ["batch_size", "emb_dim"]
                break
        warmup_onnx_session(session)
        inputs = session.run.call_args[0][1]
        assert inputs["speaker_embedding"].shape == (1, 256)


# ---------------------------------------------------------------------------
# Model cache tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelCacheHelpers:
    """_get_device_label() と _build_cache_paths() のテスト."""

    def test_device_label_cpu(self):
        assert _get_device_label("cpu") == "cpu"

    @patch(
        "onnxruntime.get_available_providers",
        return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    def test_device_label_gpu_with_cuda(self, _mock):
        assert _get_device_label("gpu") == "cuda0"

    @patch(
        "onnxruntime.get_available_providers",
        return_value=["CPUExecutionProvider"],
    )
    def test_device_label_gpu_no_cuda(self, _mock):
        assert _get_device_label("gpu") == "cpu"

    def test_build_cache_paths_cpu(self, tmp_path):
        model = tmp_path / "model.onnx"
        # _build_cache_paths now resolve(strict=True)s the model path as a
        # CodeQL py/path-injection sanitiser, so the file must exist.
        model.write_bytes(b"")
        cache, sentinel = _build_cache_paths(model, "cpu")
        assert cache == (tmp_path / "model.cpu.opt.onnx").resolve()
        assert sentinel == Path(str(cache) + ".ok")

    def test_build_cache_paths_cuda(self, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"")
        cache, sentinel = _build_cache_paths(model, "cuda0")
        assert cache == (tmp_path / "model.cuda0.opt.onnx").resolve()
        assert sentinel == Path(str(cache) + ".ok")

    def test_build_cache_paths_rejects_missing_model(self, tmp_path):
        """resolve(strict=True) must reject paths that do not exist — that
        contract is what makes the function safe against '..' traversal."""
        with pytest.raises(FileNotFoundError):
            _build_cache_paths(tmp_path / "missing.onnx", "cpu")


@pytest.mark.unit
class TestModelCache:
    """create_session_with_cache() のテスト."""

    def _mock_inference_session(self, tmp_path):
        """InferenceSession モックを返す side_effect 関数を生成."""
        mock_session = MagicMock(spec=onnxruntime.InferenceSession)
        mock_session.get_providers.return_value = ["CPUExecutionProvider"]

        def side_effect(path, sess_options=None, providers=None):
            # ORT がキャッシュファイルを生成することをシミュレート
            if (
                hasattr(sess_options, "optimized_model_filepath")
                and sess_options.optimized_model_filepath
            ):
                cache_p = Path(sess_options.optimized_model_filepath)
                cache_p.write_bytes(b"optimized")
            return mock_session

        return mock_session, side_effect

    def test_cache_miss_creates_cache(self, tmp_path):
        """初回ロードで .opt.onnx + .ok が生成される."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        mock_session, side_effect = self._mock_inference_session(tmp_path)

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            side_effect=side_effect,
        ):
            session = create_session_with_cache(model, device="cpu")

        assert session is mock_session
        assert (tmp_path / "model.cpu.opt.onnx").exists()
        assert (tmp_path / "model.cpu.opt.onnx.ok").exists()

    def test_cache_hit_uses_disable_all(self, tmp_path):
        """キャッシュヒット時に ORT_DISABLE_ALL でロードされる."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        cache = tmp_path / "model.cpu.opt.onnx"
        cache.write_bytes(b"optimized")
        sentinel = tmp_path / "model.cpu.opt.onnx.ok"
        sentinel.write_text("ok")

        captured: dict = {}
        mock_session = MagicMock(spec=onnxruntime.InferenceSession)

        def side_effect(path, sess_options=None, providers=None):
            captured["path"] = path
            captured["level"] = sess_options.graph_optimization_level
            return mock_session

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            side_effect=side_effect,
        ):
            session = create_session_with_cache(model, device="cpu")

        assert session is mock_session
        assert captured["path"] == str(cache)
        assert captured["level"] == onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL

    def test_incomplete_cache_deleted(self, tmp_path):
        """不完全キャッシュ (.opt.onnx のみ) が削除される."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        cache = tmp_path / "model.cpu.opt.onnx"
        cache.write_bytes(b"incomplete")
        # sentinel なし

        mock_session, side_effect = self._mock_inference_session(tmp_path)
        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            side_effect=side_effect,
        ):
            create_session_with_cache(model, device="cpu")

        # 元の不完全キャッシュは削除され、新しいキャッシュ + sentinel が作成される
        assert (tmp_path / "model.cpu.opt.onnx.ok").exists()

    def test_cache_hit_load_failure_fallback(self, tmp_path):
        """キャッシュファイル破損時にキャッシュ削除+再ビルドにフォールバック."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        cache = tmp_path / "model.cpu.opt.onnx"
        cache.write_bytes(b"corrupted")
        sentinel = tmp_path / "model.cpu.opt.onnx.ok"
        sentinel.write_text("ok")

        call_count = 0
        mock_session = MagicMock(spec=onnxruntime.InferenceSession)

        def side_effect(path, sess_options=None, providers=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 1回目: キャッシュからロード → 失敗
                raise RuntimeError("corrupted cache")
            # 2回目: 元モデルからロード → 成功
            if (
                hasattr(sess_options, "optimized_model_filepath")
                and sess_options.optimized_model_filepath
            ):
                Path(sess_options.optimized_model_filepath).write_bytes(b"rebuilt")
            return mock_session

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            side_effect=side_effect,
        ):
            session = create_session_with_cache(model, device="cpu")

        assert session is mock_session
        assert call_count == 2  # 1回目失敗 + 2回目成功

    @patch.dict("os.environ", {"PIPER_DISABLE_CACHE": "1"})
    def test_disable_cache_env(self, tmp_path):
        """PIPER_DISABLE_CACHE=1 でキャッシュ生成なし."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        mock_session = MagicMock(spec=onnxruntime.InferenceSession)

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            return_value=mock_session,
        ):
            create_session_with_cache(model, device="cpu")

        assert not (tmp_path / "model.cpu.opt.onnx").exists()
        assert not (tmp_path / "model.cpu.opt.onnx.ok").exists()

    @patch.dict("os.environ", {"PIPER_DISABLE_CACHE": "true"})
    def test_disable_cache_env_true(self, tmp_path):
        """PIPER_DISABLE_CACHE=true でキャッシュ生成なし."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        mock_session = MagicMock(spec=onnxruntime.InferenceSession)

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            return_value=mock_session,
        ):
            create_session_with_cache(model, device="cpu")

        assert not (tmp_path / "model.cpu.opt.onnx").exists()

    @patch.dict("os.environ", {"PIPER_DISABLE_CACHE": "yes"})
    def test_disable_cache_env_yes(self, tmp_path):
        """PIPER_DISABLE_CACHE=yes でキャッシュ生成なし."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        mock_session = MagicMock(spec=onnxruntime.InferenceSession)

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            return_value=mock_session,
        ):
            create_session_with_cache(model, device="cpu")

        assert not (tmp_path / "model.cpu.opt.onnx").exists()


@pytest.mark.unit
class TestVoiceCacheParity:
    """voice.py インライン実装と ort_utils.py の命名規則同期を検証."""

    def test_cache_path_naming_cpu(self, tmp_path):
        model = tmp_path / "model.onnx"
        # The strict resolve in _build_cache_paths needs the file to exist;
        # voice.py applies the same resolve before constructing its cache
        # path, so compare both against the resolved canonical form.
        model.write_bytes(b"")
        ort_cache, ort_sentinel = _build_cache_paths(model, "cpu")
        voice_cache = model.resolve().with_suffix(".cpu.opt.onnx")
        voice_sentinel = Path(str(voice_cache) + ".ok")
        assert ort_cache == voice_cache
        assert ort_sentinel == voice_sentinel

    def test_cache_path_naming_cuda(self, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"")
        ort_cache, ort_sentinel = _build_cache_paths(model, "cuda0")
        voice_cache = model.resolve().with_suffix(".cuda0.opt.onnx")
        voice_sentinel = Path(str(voice_cache) + ".ok")
        assert ort_cache == voice_cache
        assert ort_sentinel == voice_sentinel


# ---------------------------------------------------------------------------
# Concurrent cache race tests
# ---------------------------------------------------------------------------
#
# Audit finding: ``create_session_with_cache`` writes the optimized model
# (``.opt.onnx``) and sentinel (``.ok``) in two separate, non-atomic steps.
# Two processes hitting a fresh model concurrently can interleave such that
# one process observes an in-flight ``.opt.onnx`` without ``.ok``, deletes
# it, and races a peer that just wrote it. These tests pin the *current*
# observable behavior so future hardening (atomic rename, fcntl lock, etc.)
# does not regress the contract silently.


# Module-level worker for multiprocessing.  Defined at module scope (not
# nested in a class) so it is picklable on macOS/Windows ``spawn`` start
# methods.
def _concurrent_cache_worker(
    model_path_str: str, device: str, result_queue: "multiprocessing.Queue"
) -> None:
    """Worker process: import ort_utils fresh and call cache creation.

    Uses a real (tiny) ONNX file produced by the parent so each subprocess
    truly invokes onnxruntime.InferenceSession.  Reports outcome via queue.
    """
    try:
        # Re-import inside child so freshly forked/spawned interpreter has
        # the module loaded with no leaked patches.
        from piper_train.ort_utils import (  # local import (subprocess fresh)
            create_session_with_cache as _create,
        )

        sess = _create(Path(model_path_str), device=device)
        result_queue.put(
            {"ok": True, "providers": list(sess.get_providers()), "pid": os.getpid()}
        )
    except Exception as exc:  # pylint: disable=broad-except
        result_queue.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _make_real_tiny_onnx(path: Path) -> None:
    """Create a real, valid ONNX model file at *path* (Identity op).

    A real model is required because ``InferenceSession`` will reject a
    ``b"dummy"`` byte blob.  We use ``onnx`` if available, otherwise
    fall back to ``skip``.
    """
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper

    inp = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])
    out = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])
    node = helper.make_node("Identity", ["x"], ["y"])
    graph = helper.make_graph([node], "tiny", [inp], [out])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 7  # broadly compatible
    onnx.save(model, str(path))


@pytest.mark.unit
class TestCacheConcurrentRace:
    """Race conditions / sentinel parsing for ``create_session_with_cache``.

    These tests pin the current observable behavior of the cache path:
    parallel callers must each obtain a valid session, and recovery from
    a partial write (``.opt.onnx`` present without ``.ok``) is automatic.
    The sentinel content check is *existence-only* by design (matching
    Rust/Go/C# runtimes); whitespace/case in ``.ok`` is intentionally
    irrelevant and this is pinned by ``test_sentinel_with_extra_whitespace``.
    """

    @pytest.mark.timeout(60)
    @pytest.mark.skipif(
        sys.platform != "linux",
        reason=(
            "Linux-only: ORT's optimized-model cache reuse via .opt.onnx + .ok "
            "is sensitive to filesystem semantics. On Windows, mid-write "
            "lock contention reliably reproduces 'ModelRequiresCompilation: "
            "SystemError : 13'. On macOS APFS, similar timing-dependent "
            "failures appear in CI runners. The cache *itself* is exercised "
            "by the single-process tests on all platforms — this test is "
            "specifically the race-detector and only Linux's POSIX "
            "rename + tmpfs guarantees the deterministic behavior we pin."
        ),
    )
    def test_concurrent_cache_creation_no_corruption(self, tmp_path):
        """Two processes concurrently calling ``create_session_with_cache``
        for the same fresh model must both obtain a valid session and the
        resulting ``.opt.onnx`` + ``.ok`` files must not be corrupted.

        Pins: at least one process produces a healthy cache+sentinel pair,
        and neither process raises an unhandled exception.  Specifically
        does *not* guarantee that exactly one process writes the cache
        (current code allows both to attempt it; ORT handles concurrent
        write in practice via filesystem semantics).
        """
        model = tmp_path / "model.onnx"
        _make_real_tiny_onnx(model)

        # ``spawn`` is the safe default on macOS and is forced here so the
        # test runs identically across platforms.
        ctx = multiprocessing.get_context("spawn")
        queue: multiprocessing.Queue = ctx.Queue()
        procs = [
            ctx.Process(
                target=_concurrent_cache_worker,
                args=(str(model), "cpu", queue),
            )
            for _ in range(2)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=45)

        # Both must have terminated cleanly.
        for p in procs:
            assert not p.is_alive(), "concurrent worker did not finish"
            assert p.exitcode == 0, f"worker exited with {p.exitcode}"

        results = []
        while not queue.empty():
            results.append(queue.get_nowait())
        assert len(results) == 2, f"expected 2 results, got {results}"
        for r in results:
            assert r["ok"], f"worker reported failure: {r}"
            assert "CPUExecutionProvider" in r["providers"]

        # Final state: cache + sentinel must be consistent.  Either both
        # exist (cache hit landed) or neither does (cache disabled by
        # filesystem rules).  Pinning the "both-or-neither" invariant —
        # the bug being protected against is "cache without sentinel".
        cache_path, sentinel_path = _build_cache_paths(model, "cpu")
        if cache_path.exists():
            assert sentinel_path.exists(), (
                "RACE WINDOW: .opt.onnx present without .ok sentinel — "
                "next caller will delete the cache file"
            )
            # Cache file must be non-empty (not a 0-byte interrupted write).
            assert cache_path.stat().st_size > 0

    def test_concurrent_cache_partial_write_recovery(self, tmp_path):
        """Simulate a crash mid-write: ``.opt.onnx`` exists but ``.ok``
        does not.  The next call must detect the missing sentinel,
        delete the orphan cache, and rebuild successfully.
        """
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        cache_path, sentinel_path = _build_cache_paths(model, "cpu")

        # Pre-condition: simulate prior crash mid-write.
        cache_path.write_bytes(b"partial-write-from-crashed-process")
        assert cache_path.exists()
        assert not sentinel_path.exists()

        mock_session = MagicMock(spec=onnxruntime.InferenceSession)
        seen: dict = {"opt_path": None}

        def side_effect(path, sess_options=None, providers=None):
            # ORT sees the cleaned environment: cache should NOT exist
            # at the time of InferenceSession() construction (because
            # the partial-cache cleanup in create_session_with_cache
            # ran before this).  Capture both the path argued and the
            # cache state for assertion.
            seen["opt_path"] = (
                getattr(sess_options, "optimized_model_filepath", None)
                if sess_options
                else None
            )
            seen["cache_existed_at_call"] = cache_path.exists()
            if sess_options is not None and getattr(
                sess_options, "optimized_model_filepath", ""
            ):
                Path(sess_options.optimized_model_filepath).write_bytes(b"rebuilt")
            return mock_session

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            side_effect=side_effect,
        ):
            session = create_session_with_cache(model, device="cpu")

        assert session is mock_session
        # The orphan partial-write was deleted before the rebuild call.
        assert seen["cache_existed_at_call"] is False
        # New cache + sentinel landed.
        assert cache_path.exists()
        assert sentinel_path.exists()
        assert cache_path.read_bytes() == b"rebuilt"

    def test_sentinel_with_extra_whitespace(self, tmp_path):
        """Pin the *existence-only* sentinel check.

        The sentinel file is currently treated as a presence flag — its
        content is never parsed by ``create_session_with_cache``.  Files
        with ``"ok\\n"``, ``" ok "``, or even arbitrary garbage are
        accepted.  Lockstep with Rust/Go/C# runtimes which also do
        existence-only checks (per ``ort_session/contract.json``).

        If a future change adds content parsing, this test breaks
        immediately and the parity contract must be updated in lockstep.
        """
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        cache_path, sentinel_path = _build_cache_paths(model, "cpu")
        cache_path.write_bytes(b"optimized")

        # Variants that are technically not "ok" but currently accepted.
        for sentinel_content in ("ok\n", " ok ", "OK", "garbage", ""):
            sentinel_path.write_text(sentinel_content)
            captured: dict = {}
            mock_session = MagicMock(spec=onnxruntime.InferenceSession)

            def side_effect(path, sess_options=None, providers=None):
                captured["path"] = path
                captured["level"] = sess_options.graph_optimization_level
                return mock_session

            with patch(
                "piper_train.ort_utils.onnxruntime.InferenceSession",
                side_effect=side_effect,
            ):
                session = create_session_with_cache(model, device="cpu")

            assert session is mock_session
            # Cache hit triggered → ORT_DISABLE_ALL used (loaded from cache).
            assert captured["path"] == str(cache_path), (
                f"Sentinel content {sentinel_content!r} should not affect "
                f"cache-hit dispatch (existence-only contract)"
            )
            assert (
                captured["level"] == onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
            )
