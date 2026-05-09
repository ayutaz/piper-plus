"""Tests for ONNX Runtime session utilities (ort_utils.py).

Verifies that create_session_options() produces settings aligned with
the C#/Rust engine implementations and that get_providers() returns
the correct execution providers for each device type.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import onnxruntime
import pytest

from piper_train.ort_utils import (
    _build_cache_paths,
    _get_device_label,
    _get_logical_core_count,
    _probe_session,
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

    def test_device_label_gpu_no_cuda(self):
        # 'gpu' は 'cuda' の後方互換別名のため、CUDA 非利用時でもラベルは 'cuda0'。
        # キャッシュパスはデバイス意図に基づき決まる（利用可能性は get_providers() が担当）。
        assert _get_device_label("gpu") == "cuda0"

    def test_build_cache_paths_cpu(self, tmp_path):
        model = tmp_path / "model.onnx"
        cache, sentinel = _build_cache_paths(model, "cpu")
        assert cache == tmp_path / "model.cpu.opt.onnx"
        assert sentinel == Path(str(cache) + ".ok")

    def test_build_cache_paths_cuda(self, tmp_path):
        model = tmp_path / "model.onnx"
        cache, sentinel = _build_cache_paths(model, "cuda0")
        assert cache == tmp_path / "model.cuda0.opt.onnx"
        assert sentinel == Path(str(cache) + ".ok")


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
        ort_cache, ort_sentinel = _build_cache_paths(model, "cpu")
        voice_cache = model.with_suffix(".cpu.opt.onnx")
        voice_sentinel = Path(str(voice_cache) + ".ok")
        assert ort_cache == voice_cache
        assert ort_sentinel == voice_sentinel

    def test_cache_path_naming_cuda(self, tmp_path):
        model = tmp_path / "model.onnx"
        ort_cache, ort_sentinel = _build_cache_paths(model, "cuda0")
        voice_cache = model.with_suffix(".cuda0.opt.onnx")
        voice_sentinel = Path(str(voice_cache) + ".ok")
        assert ort_cache == voice_cache
        assert ort_sentinel == voice_sentinel


from unittest.mock import patch  # noqa: E402  (already imported above, re-import for clarity)


@pytest.mark.unit
class TestGetProviders:
    """get_providers() の実行プロバイダー選択テスト."""

    def test_cpu_returns_cpu_ep(self):
        result = get_providers("cpu")
        assert result == ["CPUExecutionProvider"]

    def test_auto_with_no_gpu_returns_cpu(self):
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            result = get_providers("auto")
        assert result == ["CPUExecutionProvider"]

    def test_auto_detects_cuda(self):
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result[0] == "CUDAExecutionProvider"
        assert "CPUExecutionProvider" in result

    def test_auto_detects_coreml_when_no_cuda(self):
        available = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        first = result[0]
        ep_name = first[0] if isinstance(first, tuple) else first
        assert ep_name == "CoreMLExecutionProvider"

    def test_auto_detects_directml_when_no_cuda_coreml(self):
        available = ["DmlExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result[0] == "DmlExecutionProvider"

    def test_explicit_cuda_returns_cuda_ep(self):
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("cuda")
        assert any(
            ep == "CUDAExecutionProvider" or
            (isinstance(ep, tuple) and ep[0] == "CUDAExecutionProvider")
            for ep in result
        )

    def test_explicit_coreml_returns_coreml_ep(self):
        available = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("coreml")
        ep_names = [ep[0] if isinstance(ep, tuple) else ep for ep in result]
        assert "CoreMLExecutionProvider" in ep_names

    def test_explicit_directml_returns_dml_ep(self):
        available = ["DmlExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("directml")
        assert any(
            ep == "DmlExecutionProvider" or
            (isinstance(ep, tuple) and ep[0] == "DmlExecutionProvider")
            for ep in result
        )

    def test_unavailable_ep_falls_back_to_cpu(self):
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            result = get_providers("cuda")
        assert result == ["CPUExecutionProvider"]

    def test_env_var_overrides_device_param(self, monkeypatch):
        monkeypatch.setenv("PIPER_EXECUTION_PROVIDER", "cpu")
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result == ["CPUExecutionProvider"]

    def test_env_var_selects_coreml(self, monkeypatch):
        monkeypatch.setenv("PIPER_EXECUTION_PROVIDER", "coreml")
        available = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        ep_names = [ep[0] if isinstance(ep, tuple) else ep for ep in result]
        assert "CoreMLExecutionProvider" in ep_names

    def test_tensorrt_excluded_from_auto(self):
        available = ["TensorrtExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result == ["CPUExecutionProvider"]

    def test_unknown_device_falls_back_to_cpu(self):
        result = get_providers("vulkan")
        assert result == ["CPUExecutionProvider"]

    def test_gpu_alias_works_as_cuda(self):
        """'gpu' は 'cuda' の後方互換別名として機能すること."""
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("gpu")
        assert any(
            ep == "CUDAExecutionProvider" or
            (isinstance(ep, tuple) and ep[0] == "CUDAExecutionProvider")
            for ep in result
        )


@pytest.mark.unit
class TestGetDeviceLabel:
    """_get_device_label() のキャッシュラベルテスト."""

    def test_cpu_returns_cpu(self):
        result = _get_device_label("cpu")
        assert result == "cpu"

    def test_auto_no_gpu_returns_cpu(self):
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            result = _get_device_label("auto")
        assert result == "cpu"

    def test_auto_with_cuda_returns_cuda0(self):
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = _get_device_label("auto")
        assert result == "cuda0"

    def test_explicit_cuda_returns_cuda0(self):
        result = _get_device_label("cuda")
        assert result == "cuda0"

    def test_explicit_cuda1_returns_cuda1(self):
        result = _get_device_label("cuda:1")
        assert result == "cuda1"

    def test_explicit_coreml_returns_coreml(self):
        result = _get_device_label("coreml")
        assert result == "coreml"

    def test_explicit_directml_returns_directml0(self):
        result = _get_device_label("directml")
        assert result == "directml0"

    def test_explicit_directml1_returns_directml1(self):
        result = _get_device_label("directml:1")
        assert result == "directml1"

    def test_explicit_openvino_returns_openvino(self):
        result = _get_device_label("openvino")
        assert result == "openvino"

    def test_explicit_tensorrt_returns_tensorrt0(self):
        result = _get_device_label("tensorrt")
        assert result == "tensorrt0"

    def test_env_var_overrides_device_label(self, monkeypatch):
        monkeypatch.setenv("PIPER_EXECUTION_PROVIDER", "coreml")
        result = _get_device_label("auto")
        assert result == "coreml"

    def test_gpu_alias_returns_cuda0(self):
        """'gpu' は 'cuda' の後方互換別名。ラベルは 'cuda0' を返すこと."""
        result = _get_device_label("gpu")
        assert result == "cuda0"


@pytest.mark.unit
class TestEpProbeAndFallback:
    """_probe_session() と create_session_with_cache() の EP フォールバックテスト."""

    def test_probe_returns_true_on_success(self):
        """sess.run() が成功したら True を返す."""
        mock_sess = MagicMock(spec=onnxruntime.InferenceSession)
        mock_sess.get_inputs.return_value = [
            MagicMock(name="input"),
            MagicMock(name="input_lengths"),
            MagicMock(name="scales"),
        ]
        for inp in mock_sess.get_inputs.return_value:
            inp.name = inp.name  # MagicMock の .name は特殊属性なので明示設定
        mock_sess.get_inputs.return_value[0].name = "input"
        mock_sess.get_inputs.return_value[1].name = "input_lengths"
        mock_sess.get_inputs.return_value[2].name = "scales"
        mock_sess.run.return_value = [np.zeros((1, 1, 1, 100))]
        assert _probe_session(mock_sess) is True

    def test_probe_returns_false_on_run_failure(self):
        """sess.run() が例外を送出したら False を返す."""
        mock_sess = MagicMock(spec=onnxruntime.InferenceSession)
        mock_sess.get_inputs.return_value = []
        mock_sess.run.side_effect = RuntimeError("CoreML: zero-element tensor")
        assert _probe_session(mock_sess) is False

    def test_create_session_falls_back_to_cpu_when_probe_fails(self, tmp_path):
        """非 CPU EP でプローブが失敗したとき CPU EP で再作成される."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        # 1 回目: CoreML EP セッション (probe 失敗), 2 回目: CPU EP セッション
        coreml_sess = MagicMock(spec=onnxruntime.InferenceSession)
        coreml_sess.get_inputs.return_value = []
        coreml_sess.run.side_effect = RuntimeError("CoreML not supported")

        cpu_sess = MagicMock(spec=onnxruntime.InferenceSession)

        call_providers = []

        def _ep_name(ep):
            return ep[0] if isinstance(ep, tuple) else ep

        def side_effect(path, sess_options=None, providers=None):
            call_providers.append(providers)
            if providers and _ep_name(providers[0]) == "CoreMLExecutionProvider":
                return coreml_sess
            return cpu_sess

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            side_effect=side_effect,
        ):
            result = create_session_with_cache(
                model,
                device="coreml",
            )

        assert result is cpu_sess
        # 最後のフォールバック呼び出しが CPU EP のみであること
        assert call_providers[-1] == ["CPUExecutionProvider"]

    def test_create_session_no_probe_for_cpu_ep(self, tmp_path):
        """CPU EP では probe を実行しない（run が呼ばれない）."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        mock_sess = MagicMock(spec=onnxruntime.InferenceSession)

        with patch(
            "piper_train.ort_utils.onnxruntime.InferenceSession",
            return_value=mock_sess,
        ):
            create_session_with_cache(model, device="cpu")

        mock_sess.run.assert_not_called()
