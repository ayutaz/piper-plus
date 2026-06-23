"""
M3: 推論パイプラインのテスト
- ONNX export zero-shot対応
- infer_onnx.py speaker_embedding対応
"""

import numpy as np
import pytest


try:
    import torch
except ImportError:
    torch = None

try:
    import onnxruntime
except ImportError:
    onnxruntime = None

try:
    import onnxscript  # noqa: F401

    has_onnxscript = True
except ImportError:
    has_onnxscript = False

requires_onnx_export = pytest.mark.skipif(
    onnxruntime is None or not has_onnxscript,
    reason="onnxruntime and onnxscript required for ONNX export tests",
)

pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")

if torch is not None:
    from piper_train.vits.models import SynthesizerTrn

# 最小限のモデルパラメータ (test_zero_shot.py の MODEL_PARAMS と同じ)
MODEL_PARAMS = {
    "n_vocab": 50,
    "spec_channels": 513,
    "segment_size": 8192,
    "inter_channels": 192,
    "hidden_channels": 192,
    "filter_channels": 768,
    "n_heads": 2,
    "n_layers": 6,
    "kernel_size": 3,
    "p_dropout": 0.1,
    "resblock": "1",
    "resblock_kernel_sizes": [3, 7, 11],
    "resblock_dilation_sizes": [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
    "upsample_rates": [8, 8, 2, 2],
    "upsample_initial_channel": 512,
    "upsample_kernel_sizes": [16, 16, 4, 4],
    "prosody_dim": 16,
}


class TestExportOnnxZeroShot:
    """Zero-shot モデルの ONNX エクスポートテスト"""

    @pytest.mark.unit
    @requires_onnx_export
    def test_export_zero_shot_model(self, tmp_path):
        """Zero-shot モデルを ONNX エクスポートし、speaker_embedding で推論できる"""
        torch.manual_seed(42)

        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=2,
            gin_channels=512,
        )
        model.eval()
        with torch.no_grad():
            model.dec.remove_weight_norm()

        # Enable ONNX export mode (decoder must also be set so MBiSTFT
        # returns fullband only, not a (fullband, subbands) tuple).
        model.onnx_export_mode = True
        if hasattr(model, "dp"):
            model.dp.onnx_export_mode = True
        if hasattr(model, "dec"):
            model.dec.onnx_export_mode = True

        from piper_train.vits import commons

        def infer_forward(
            text,
            text_lengths,
            scales,
            sid=None,
            prosody_features=None,
            speaker_embedding=None,
        ):
            length_scale = scales[1]
            noise_scale_w = scales[2]
            g = model._get_speaker_condition(speaker_embeddings=speaker_embedding)
            x, m_p, logs_p, x_mask = model.enc_p(text, text_lengths, g=g)
            x_dp = model._prepare_prosody_input(x, x_mask, prosody_features)
            logw = model.dp(x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w)
            w = torch.exp(logw) * x_mask * length_scale
            w_ceil = torch.ceil(w)
            y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
            y_mask = torch.unsqueeze(
                commons.sequence_mask(y_lengths, y_lengths.max()), 1
            ).type_as(x_mask)
            attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
            attn = commons.generate_path(w_ceil, attn_mask)
            m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
            logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(
                1, 2
            )
            z_p = m_p
            z = model.flow(z_p, y_mask, g=g, reverse=True)
            o = model.dec((z * y_mask), g=g)
            return o.unsqueeze(1), torch.zeros(1)

        model.forward = infer_forward

        # Prepare dummy inputs
        dummy_input_length = 50
        sequences = torch.randint(0, 50, (1, dummy_input_length), dtype=torch.long)
        sequence_lengths = torch.LongTensor([dummy_input_length])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        dummy_speaker_embedding = torch.randn(1, 192, dtype=torch.float32)
        prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

        onnx_path = tmp_path / "zero_shot_model.onnx"

        torch.onnx.export(
            model=model,
            args=(
                sequences,
                sequence_lengths,
                scales,
                None,
                prosody_features,
                dummy_speaker_embedding,
            ),
            f=str(onnx_path),
            verbose=False,
            opset_version=15,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "prosody_features",
                "speaker_embedding",
            ],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "speaker_embedding": {0: "batch_size"},
                "output": {0: "batch_size", 1: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            dynamo=False,
        )

        # Load with onnxruntime
        session = onnxruntime.InferenceSession(str(onnx_path))
        input_names = [inp.name for inp in session.get_inputs()]

        # Check input names
        assert "speaker_embedding" in input_names, (
            "speaker_embedding should be in ONNX input names"
        )
        assert "sid" not in input_names, (
            "sid should NOT be in zero-shot ONNX input names"
        )

        # Run inference with speaker_embedding
        text_np = np.expand_dims(
            np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.int64), 0
        )
        text_lengths_np = np.array([text_np.shape[1]], dtype=np.int64)
        scales_np = np.array([0.667, 1.0, 0.8], dtype=np.float32)
        spk_emb_np = np.random.randn(1, 192).astype(np.float32)
        prosody_np = np.zeros((1, text_np.shape[1], 3), dtype=np.int64)

        inputs = {
            "input": text_np,
            "input_lengths": text_lengths_np,
            "scales": scales_np,
            "speaker_embedding": spk_emb_np,
            "prosody_features": prosody_np,
        }
        outputs = session.run(None, inputs)
        audio = outputs[0]
        assert audio is not None
        assert audio.ndim >= 1
        assert np.isfinite(audio).all(), "ONNX output contains NaN or Inf"

    @pytest.mark.unit
    @requires_onnx_export
    def test_export_multispeaker_regression(self, tmp_path):
        """Multispeaker モデルでエクスポートし、speaker_embedding で推論できることを確認.

        Note: emb_g (nn.Embedding) は廃止。全speaker conditioningは spk_proj MLP 経由。
        multispeaker でも speaker_embedding 入力を使用する。
        """
        torch.manual_seed(42)

        model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        model.eval()
        with torch.no_grad():
            model.dec.remove_weight_norm()

        model.onnx_export_mode = True
        if hasattr(model, "dp"):
            model.dp.onnx_export_mode = True
        if hasattr(model, "dec"):
            model.dec.onnx_export_mode = True

        from piper_train.vits import commons

        def infer_forward(
            text, text_lengths, scales, prosody_features=None, speaker_embedding=None
        ):
            g = model._get_speaker_condition(speaker_embeddings=speaker_embedding)
            x, m_p, logs_p, x_mask = model.enc_p(text, text_lengths, g=g)
            x_dp = model._prepare_prosody_input(x, x_mask, prosody_features)
            logw = model.dp(x_dp, x_mask, g=g, reverse=True, noise_scale=0.8)
            w = torch.exp(logw) * x_mask * 1.0
            w_ceil = torch.ceil(w)
            y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
            y_mask = torch.unsqueeze(
                commons.sequence_mask(y_lengths, y_lengths.max()), 1
            ).type_as(x_mask)
            attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
            attn = commons.generate_path(w_ceil, attn_mask)
            m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
            logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(
                1, 2
            )
            z_p = m_p
            z = model.flow(z_p, y_mask, g=g, reverse=True)
            o = model.dec((z * y_mask), g=g)
            return o.unsqueeze(1), torch.zeros(1)

        model.forward = infer_forward

        dummy_input_length = 50
        sequences = torch.randint(0, 50, (1, dummy_input_length), dtype=torch.long)
        sequence_lengths = torch.LongTensor([dummy_input_length])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        dummy_speaker_embedding = torch.randn(1, 192, dtype=torch.float32)
        prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

        onnx_path = tmp_path / "multispeaker_model.onnx"

        torch.onnx.export(
            model=model,
            args=(
                sequences,
                sequence_lengths,
                scales,
                prosody_features,
                dummy_speaker_embedding,
            ),
            f=str(onnx_path),
            verbose=False,
            opset_version=15,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "prosody_features",
                "speaker_embedding",
            ],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "speaker_embedding": {0: "batch_size"},
                "output": {0: "batch_size", 1: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            dynamo=False,
        )

        session = onnxruntime.InferenceSession(str(onnx_path))
        input_names = [inp.name for inp in session.get_inputs()]

        assert "speaker_embedding" in input_names, (
            "speaker_embedding should be in multispeaker ONNX input names"
        )

    @pytest.mark.unit
    @requires_onnx_export
    def test_zero_shot_onnx_model_size(self, tmp_path):
        """n_speakers=2 と n_speakers=20 の ONNX モデルサイズ差 < 4MB.

        Both use spk_proj MLP (no emb_g), so size difference is minimal.
        """
        torch.manual_seed(42)

        from piper_train.vits import commons

        # --- Small multi-speaker model (n_speakers=2) ---
        zs_model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=2,
            gin_channels=512,
        )
        zs_model.eval()
        with torch.no_grad():
            zs_model.dec.remove_weight_norm()

        zs_model.onnx_export_mode = True
        if hasattr(zs_model, "dp"):
            zs_model.dp.onnx_export_mode = True
        if hasattr(zs_model, "dec"):
            zs_model.dec.onnx_export_mode = True

        def zs_infer_forward(
            text,
            text_lengths,
            scales,
            prosody_features=None,
            speaker_embedding=None,
        ):
            length_scale = scales[1]
            noise_scale_w = scales[2]
            g = zs_model._get_speaker_condition(speaker_embeddings=speaker_embedding)
            x, m_p, logs_p, x_mask = zs_model.enc_p(text, text_lengths, g=g)
            x_dp = zs_model._prepare_prosody_input(x, x_mask, prosody_features)
            logw = zs_model.dp(x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w)
            w = torch.exp(logw) * x_mask * length_scale
            w_ceil = torch.ceil(w)
            y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
            y_mask = torch.unsqueeze(
                commons.sequence_mask(y_lengths, y_lengths.max()), 1
            ).type_as(x_mask)
            attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
            attn = commons.generate_path(w_ceil, attn_mask)
            m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
            logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(
                1, 2
            )
            z_p = m_p
            z = zs_model.flow(z_p, y_mask, g=g, reverse=True)
            o = zs_model.dec((z * y_mask), g=g)
            return o.unsqueeze(1), torch.zeros(1)

        zs_model.forward = zs_infer_forward

        dummy_input_length = 50
        sequences = torch.randint(0, 50, (1, dummy_input_length), dtype=torch.long)
        sequence_lengths = torch.LongTensor([dummy_input_length])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        dummy_speaker_embedding = torch.randn(1, 192, dtype=torch.float32)
        prosody_features = torch.zeros(1, dummy_input_length, 3, dtype=torch.long)

        zs_onnx_path = tmp_path / "zs_model.onnx"
        torch.onnx.export(
            model=zs_model,
            args=(
                sequences,
                sequence_lengths,
                scales,
                prosody_features,
                dummy_speaker_embedding,
            ),
            f=str(zs_onnx_path),
            verbose=False,
            opset_version=15,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "prosody_features",
                "speaker_embedding",
            ],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "speaker_embedding": {0: "batch_size"},
                "output": {0: "batch_size", 1: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            dynamo=False,
        )

        # --- Larger multi-speaker model (n_speakers=20) ---
        torch.manual_seed(42)
        ms_model = SynthesizerTrn(
            **MODEL_PARAMS,
            n_speakers=20,
            gin_channels=512,
        )
        ms_model.eval()
        with torch.no_grad():
            ms_model.dec.remove_weight_norm()

        ms_model.onnx_export_mode = True
        if hasattr(ms_model, "dp"):
            ms_model.dp.onnx_export_mode = True
        if hasattr(ms_model, "dec"):
            ms_model.dec.onnx_export_mode = True

        def ms_infer_forward(
            text, text_lengths, scales, prosody_features=None, speaker_embedding=None
        ):
            g = ms_model._get_speaker_condition(speaker_embeddings=speaker_embedding)
            x, m_p, logs_p, x_mask = ms_model.enc_p(text, text_lengths, g=g)
            x_dp = ms_model._prepare_prosody_input(x, x_mask, prosody_features)
            logw = ms_model.dp(x_dp, x_mask, g=g, reverse=True, noise_scale=0.8)
            w = torch.exp(logw) * x_mask * 1.0
            w_ceil = torch.ceil(w)
            y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
            y_mask = torch.unsqueeze(
                commons.sequence_mask(y_lengths, y_lengths.max()), 1
            ).type_as(x_mask)
            attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
            attn = commons.generate_path(w_ceil, attn_mask)
            m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
            logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(
                1, 2
            )
            z_p = m_p
            z = ms_model.flow(z_p, y_mask, g=g, reverse=True)
            o = ms_model.dec((z * y_mask), g=g)
            return o.unsqueeze(1), torch.zeros(1)

        ms_model.forward = ms_infer_forward

        ms_onnx_path = tmp_path / "ms_model.onnx"
        torch.onnx.export(
            model=ms_model,
            args=(
                sequences,
                sequence_lengths,
                scales,
                prosody_features,
                dummy_speaker_embedding,
            ),
            f=str(ms_onnx_path),
            verbose=False,
            opset_version=15,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "prosody_features",
                "speaker_embedding",
            ],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "speaker_embedding": {0: "batch_size"},
                "output": {0: "batch_size", 1: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            dynamo=False,
        )

        # Compare sizes
        zs_size = zs_onnx_path.stat().st_size
        ms_size = ms_onnx_path.stat().st_size
        size_diff_mb = abs(zs_size - ms_size) / (1024 * 1024)

        assert size_diff_mb < 4.0, (
            f"ONNX model size difference is {size_diff_mb:.2f} MB, "
            f"expected < 4 MB (small: {zs_size} bytes, large: {ms_size} bytes)"
        )


class TestSpeakerEmbeddingNpyLoad:
    """speaker_embedding の allow_pickle=False テスト"""

    @pytest.mark.unit
    def test_npy_load_allow_pickle_false(self, tmp_path):
        """正常なembedding .npyをallow_pickle=Falseで読み込めること"""
        emb = np.random.randn(192).astype(np.float32)
        npy_path = tmp_path / "speaker.npy"
        np.save(str(npy_path), emb)

        loaded = np.load(str(npy_path), allow_pickle=False)
        assert loaded.shape == (192,)
        assert loaded.dtype == np.float32
        np.testing.assert_array_almost_equal(loaded, emb)

    @pytest.mark.unit
    def test_npy_2d_load_allow_pickle_false(self, tmp_path):
        """2D embedding .npyをallow_pickle=Falseで読み込めること"""
        emb = np.random.randn(1, 192).astype(np.float32)
        npy_path = tmp_path / "speaker_2d.npy"
        np.save(str(npy_path), emb)

        loaded = np.load(str(npy_path), allow_pickle=False)
        assert loaded.shape == (1, 192)
        assert loaded.dtype == np.float32


class TestExportOnnxInputNames:
    """export_onnx.py の input_names 構築ロジックのテスト"""

    @staticmethod
    def _build_input_names(use_zero_shot: bool, num_speakers: int, has_prosody: bool):
        """export_onnx.py のinput_names構築ロジックをインライン再現"""
        input_names = ["input", "input_lengths", "scales"]
        if use_zero_shot:
            input_names.append("speaker_embedding")
            if has_prosody:
                input_names.append("prosody_features")
        elif num_speakers > 1:
            input_names.append("sid")
            if has_prosody:
                input_names.append("prosody_features")
        elif has_prosody:
            input_names.append("prosody_features")
        return input_names

    @pytest.mark.unit
    def test_zero_shot_with_prosody(self):
        """zero-shot + prosody: speaker_embedding の後に prosody_features"""
        names = self._build_input_names(
            use_zero_shot=True, num_speakers=1, has_prosody=True
        )
        assert names == [
            "input",
            "input_lengths",
            "scales",
            "speaker_embedding",
            "prosody_features",
        ]

    @pytest.mark.unit
    def test_zero_shot_without_prosody(self):
        """zero-shot のみ（prosodyなし）: speaker_embedding"""
        names = self._build_input_names(
            use_zero_shot=True, num_speakers=1, has_prosody=False
        )
        assert names == [
            "input",
            "input_lengths",
            "scales",
            "speaker_embedding",
        ]

    @pytest.mark.unit
    def test_multispeaker_with_prosody(self):
        """multispeaker + prosody: sid, prosody_features"""
        names = self._build_input_names(
            use_zero_shot=False, num_speakers=20, has_prosody=True
        )
        assert names == [
            "input",
            "input_lengths",
            "scales",
            "sid",
            "prosody_features",
        ]

    @pytest.mark.unit
    def test_prosody_only_single_speaker(self):
        """prosody のみ（single speaker）: prosody_features"""
        names = self._build_input_names(
            use_zero_shot=False, num_speakers=1, has_prosody=True
        )
        assert names == [
            "input",
            "input_lengths",
            "scales",
            "prosody_features",
        ]

    @pytest.mark.unit
    def test_single_speaker_no_prosody(self):
        """single speaker, prosodyなし: 基本3つのみ"""
        names = self._build_input_names(
            use_zero_shot=False, num_speakers=1, has_prosody=False
        )
        assert names == [
            "input",
            "input_lengths",
            "scales",
        ]


class TestInferOnnxSpeakerEmbedding:
    """infer_onnx.py の speaker_embedding 入力処理テスト"""

    @pytest.mark.unit
    def test_speaker_embedding_input_construction(self, tmp_path):
        """1D speaker_embedding (.npy) を読み込み、reshape で [1, 192] になること"""
        emb = np.random.randn(192).astype(np.float32)
        npy_path = tmp_path / "speaker.npy"
        np.save(str(npy_path), emb)

        loaded = np.load(str(npy_path)).astype(np.float32)
        assert loaded.shape == (192,)

        # ndim==1 の場合 reshape(1, -1) で [1, 192] にする (infer_onnx.py と同じロジック)
        if loaded.ndim == 1:
            loaded = loaded.reshape(1, -1)
        assert loaded.shape == (1, 192)

    @pytest.mark.unit
    def test_speaker_embedding_shape_2d(self, tmp_path):
        """2D speaker_embedding (.npy) を読み込み、shape == (1, 192) であること"""
        emb = np.random.randn(1, 192).astype(np.float32)
        npy_path = tmp_path / "speaker_2d.npy"
        np.save(str(npy_path), emb)

        loaded = np.load(str(npy_path)).astype(np.float32)
        assert loaded.shape == (1, 192)
