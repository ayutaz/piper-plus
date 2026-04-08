"""Tests for the Speaker Encoder (ECAPA-TDNN) module.

Covers model forward pass, mel spectrogram computation, cosine similarity,
ONNX export round-trip, and evaluation utilities.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch


# ---------------------------------------------------------------------------
# ECAPA-TDNN model tests
# ---------------------------------------------------------------------------


class TestECAPATDNN:
    """Tests for the ECAPA-TDNN PyTorch model."""

    def test_output_shape(self):
        """Model produces (batch, emb_dim) output."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN(input_dim=80, channels=1024, emb_dim=256)
        model.eval()
        mel = torch.randn(2, 80, 200)
        with torch.no_grad():
            emb = model(mel)
        assert emb.shape == (2, 256)

    def test_output_l2_normalized(self):
        """Output embeddings are L2-normalized (unit norm)."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN()
        model.eval()
        mel = torch.randn(3, 80, 150)
        with torch.no_grad():
            emb = model(mel)
        norms = torch.norm(emb, p=2, dim=1)
        np.testing.assert_allclose(norms.numpy(), 1.0, atol=1e-5)

    def test_variable_time_length(self):
        """Model handles variable time-axis lengths."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN()
        model.eval()
        for t in [50, 100, 300, 500]:
            mel = torch.randn(1, 80, t)
            with torch.no_grad():
                emb = model(mel)
            assert emb.shape == (1, 256), f"Failed for time={t}"

    def test_deterministic_eval(self):
        """Same input produces same output in eval mode."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN()
        model.eval()
        mel = torch.randn(1, 80, 200)
        with torch.no_grad():
            emb1 = model(mel).numpy()
            emb2 = model(mel).numpy()
        np.testing.assert_array_equal(emb1, emb2)

    def test_small_channels(self):
        """Model works with reduced channel count for fast testing."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN(input_dim=40, channels=64, emb_dim=32, scale=8)
        model.eval()
        mel = torch.randn(2, 40, 100)
        with torch.no_grad():
            emb = model(mel)
        assert emb.shape == (2, 32)

    def test_batch_independence(self):
        """Each sample in a batch is processed independently."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN(channels=64, emb_dim=32, scale=8)
        model.eval()

        mel1 = torch.randn(1, 80, 100)
        mel2 = torch.randn(1, 80, 100)
        batch = torch.cat([mel1, mel2], dim=0)

        with torch.no_grad():
            emb_single1 = model(mel1)
            emb_single2 = model(mel2)
            emb_batch = model(batch)

        np.testing.assert_allclose(
            emb_batch[0].numpy(), emb_single1[0].numpy(), atol=1e-5
        )
        np.testing.assert_allclose(
            emb_batch[1].numpy(), emb_single2[0].numpy(), atol=1e-5
        )


# ---------------------------------------------------------------------------
# Audio utilities tests
# ---------------------------------------------------------------------------


class TestMelSpectrogram:
    """Tests for mel spectrogram computation."""

    def test_output_shape(self):
        """Mel spectrogram has correct shape (n_mels, time)."""
        from piper_train.speaker_encoder.audio_utils import compute_mel_spectrogram

        audio = np.random.randn(16000).astype(np.float32)  # 1 second at 16kHz
        mel = compute_mel_spectrogram(audio)
        assert mel.shape[0] == 80  # n_mels
        # Expected frames: 1 + (16000 - 512) // 160 = 97
        expected_frames = 1 + (16000 - 512) // 160
        assert mel.shape[1] == expected_frames

    def test_output_dtype(self):
        """Mel spectrogram is float32."""
        from piper_train.speaker_encoder.audio_utils import compute_mel_spectrogram

        audio = np.random.randn(16000).astype(np.float32)
        mel = compute_mel_spectrogram(audio)
        assert mel.dtype == np.float32

    def test_custom_params(self):
        """Custom mel parameters change output shape."""
        from piper_train.speaker_encoder.audio_utils import compute_mel_spectrogram

        audio = np.random.randn(16000).astype(np.float32)
        mel = compute_mel_spectrogram(audio, n_mels=40, n_fft=1024, hop_length=256)
        assert mel.shape[0] == 40

    def test_short_audio(self):
        """Short audio (< n_fft) is zero-padded and produces valid output."""
        from piper_train.speaker_encoder.audio_utils import compute_mel_spectrogram

        audio = np.random.randn(100).astype(np.float32)
        mel = compute_mel_spectrogram(audio)
        assert mel.shape[0] == 80
        assert mel.shape[1] >= 1

    def test_silent_audio(self):
        """Silent audio produces finite mel values (no NaN/Inf)."""
        from piper_train.speaker_encoder.audio_utils import compute_mel_spectrogram

        audio = np.zeros(16000, dtype=np.float32)
        mel = compute_mel_spectrogram(audio)
        assert np.all(np.isfinite(mel))


class TestNormalizeAudio:
    """Tests for audio peak normalization."""

    def test_peak_normalized(self):
        """Normalized audio peak is 1.0."""
        from piper_train.speaker_encoder.audio_utils import normalize_audio

        audio = np.array([0.5, -0.3, 0.2], dtype=np.float32)
        result = normalize_audio(audio)
        assert abs(np.abs(result).max() - 1.0) < 1e-6

    def test_silent_audio(self):
        """Silent audio is returned unchanged."""
        from piper_train.speaker_encoder.audio_utils import normalize_audio

        audio = np.zeros(100, dtype=np.float32)
        result = normalize_audio(audio)
        assert np.all(result == 0.0)

    def test_already_normalized(self):
        """Audio with peak=1.0 is unchanged."""
        from piper_train.speaker_encoder.audio_utils import normalize_audio

        audio = np.array([1.0, -0.5, 0.0], dtype=np.float32)
        result = normalize_audio(audio)
        np.testing.assert_allclose(result, audio, atol=1e-6)

    def test_output_dtype(self):
        """Output is float32."""
        from piper_train.speaker_encoder.audio_utils import normalize_audio

        audio = np.array([0.5, -0.3], dtype=np.float32)
        result = normalize_audio(audio)
        assert result.dtype == np.float32


class TestMelFilterbank:
    """Tests for internal mel filterbank creation."""

    def test_filterbank_shape(self):
        """Filterbank has correct shape (n_mels, n_fft//2+1)."""
        from piper_train.speaker_encoder.audio_utils import _create_mel_filterbank

        fb = _create_mel_filterbank(sr=16000, n_fft=512, n_mels=80, fmin=20.0, fmax=7600.0)
        assert fb.shape == (80, 257)  # 512 // 2 + 1 = 257

    def test_filterbank_non_negative(self):
        """All filterbank values are non-negative."""
        from piper_train.speaker_encoder.audio_utils import _create_mel_filterbank

        fb = _create_mel_filterbank(sr=16000, n_fft=512, n_mels=80, fmin=20.0, fmax=7600.0)
        assert np.all(fb >= 0)

    def test_filterbank_non_trivial(self):
        """Filterbank has non-zero entries (filters are not all empty)."""
        from piper_train.speaker_encoder.audio_utils import _create_mel_filterbank

        fb = _create_mel_filterbank(sr=16000, n_fft=512, n_mels=80, fmin=20.0, fmax=7600.0)
        assert fb.sum() > 0
        # Each mel band should have at least some non-zero entries
        assert np.all(fb.sum(axis=1) > 0)


# ---------------------------------------------------------------------------
# SpeakerEncoder API tests
# ---------------------------------------------------------------------------


class TestSpeakerEncoderSimilarity:
    """Tests for cosine similarity computation."""

    def test_identical_embeddings(self):
        """Identical embeddings have similarity = 1.0."""
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert abs(SpeakerEncoder.similarity(emb, emb) - 1.0) < 1e-6

    def test_opposite_embeddings(self):
        """Opposite embeddings have similarity = -1.0."""
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        emb1 = np.array([1.0, 0.0], dtype=np.float32)
        emb2 = np.array([-1.0, 0.0], dtype=np.float32)
        assert abs(SpeakerEncoder.similarity(emb1, emb2) - (-1.0)) < 1e-6

    def test_orthogonal_embeddings(self):
        """Orthogonal embeddings have similarity = 0.0."""
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        emb1 = np.array([1.0, 0.0], dtype=np.float32)
        emb2 = np.array([0.0, 1.0], dtype=np.float32)
        assert abs(SpeakerEncoder.similarity(emb1, emb2)) < 1e-6

    def test_zero_embedding(self):
        """Zero embedding returns similarity = 0.0."""
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        emb1 = np.array([1.0, 0.0], dtype=np.float32)
        emb2 = np.zeros(2, dtype=np.float32)
        assert SpeakerEncoder.similarity(emb1, emb2) == 0.0

    def test_random_embeddings_range(self):
        """Cosine similarity is in [-1, 1]."""
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        for _ in range(20):
            emb1 = np.random.randn(256).astype(np.float32)
            emb2 = np.random.randn(256).astype(np.float32)
            sim = SpeakerEncoder.similarity(emb1, emb2)
            assert -1.0 - 1e-6 <= sim <= 1.0 + 1e-6


class TestSpeakerEncoderPyTorch:
    """Tests for SpeakerEncoder PyTorch backend."""

    def test_from_pytorch_checkpoint(self):
        """Load from a saved state_dict checkpoint."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        # Create and save a model checkpoint
        model = ECAPATDNN(channels=64, emb_dim=32, scale=8)
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            torch.save(model.state_dict(), f.name)
            ckpt_path = f.name

        try:
            encoder = SpeakerEncoder.from_pytorch(ckpt_path)
            assert encoder._mode == "pytorch"
        finally:
            Path(ckpt_path).unlink(missing_ok=True)

    def test_from_pytorch_checkpoint_with_key(self):
        """Load from a checkpoint with 'model_state_dict' key."""
        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        model = ECAPATDNN(channels=64, emb_dim=32, scale=8)
        ckpt = {"model_state_dict": model.state_dict(), "epoch": 10}
        with tempfile.NamedTemporaryFile(suffix=".ckpt", delete=False) as f:
            torch.save(ckpt, f.name)
            ckpt_path = f.name

        try:
            encoder = SpeakerEncoder.from_pytorch(ckpt_path)
            assert encoder._mode == "pytorch"
        finally:
            Path(ckpt_path).unlink(missing_ok=True)

    def test_missing_checkpoint(self):
        """Raise FileNotFoundError for missing checkpoint."""
        from piper_train.speaker_encoder.encoder import SpeakerEncoder

        with pytest.raises(FileNotFoundError):
            SpeakerEncoder.from_pytorch("/nonexistent/path.pt")


# ---------------------------------------------------------------------------
# ONNX export round-trip test
# ---------------------------------------------------------------------------


class TestONNXExportRoundTrip:
    """Test ONNX export and loading produces matching results."""

    def test_export_and_load(self):
        """Export model to ONNX and verify output matches PyTorch."""
        onnxruntime = pytest.importorskip("onnxruntime")

        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        # Use small model for speed
        model = ECAPATDNN(channels=64, emb_dim=32, scale=8)
        model.eval()

        mel = torch.randn(1, 80, 100)

        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
            onnx_path = f.name

        try:
            # Export
            torch.onnx.export(
                model,
                (mel,),
                onnx_path,
                opset_version=17,
                input_names=["mel"],
                output_names=["embedding"],
                dynamic_axes={
                    "mel": {0: "batch_size", 2: "time"},
                    "embedding": {0: "batch_size"},
                },
                dynamo=False,
            )

            # Load ONNX
            session = onnxruntime.InferenceSession(onnx_path)
            onnx_out = session.run(
                ["embedding"],
                {"mel": mel.numpy()},
            )[0]

            # Compare
            with torch.no_grad():
                pt_out = model(mel).numpy()

            np.testing.assert_allclose(onnx_out, pt_out, atol=1e-4)
            assert onnx_out.shape == (1, 32)

        finally:
            Path(onnx_path).unlink(missing_ok=True)

    def test_onnx_dynamic_batch(self):
        """ONNX model handles variable batch sizes."""
        onnxruntime = pytest.importorskip("onnxruntime")

        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN(channels=64, emb_dim=32, scale=8)
        model.eval()

        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
            onnx_path = f.name

        try:
            mel = torch.randn(1, 80, 100)
            torch.onnx.export(
                model,
                (mel,),
                onnx_path,
                opset_version=17,
                input_names=["mel"],
                output_names=["embedding"],
                dynamic_axes={
                    "mel": {0: "batch_size", 2: "time"},
                    "embedding": {0: "batch_size"},
                },
                dynamo=False,
            )

            session = onnxruntime.InferenceSession(onnx_path)

            for batch_size in [1, 2, 4]:
                mel_np = np.random.randn(batch_size, 80, 100).astype(np.float32)
                result = session.run(["embedding"], {"mel": mel_np})[0]
                assert result.shape == (batch_size, 32)

        finally:
            Path(onnx_path).unlink(missing_ok=True)

    def test_onnx_dynamic_time(self):
        """ONNX model handles variable time-axis lengths."""
        onnxruntime = pytest.importorskip("onnxruntime")

        from piper_train.speaker_encoder.ecapa_tdnn import ECAPATDNN

        model = ECAPATDNN(channels=64, emb_dim=32, scale=8)
        model.eval()

        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
            onnx_path = f.name

        try:
            mel = torch.randn(1, 80, 100)
            torch.onnx.export(
                model,
                (mel,),
                onnx_path,
                opset_version=17,
                input_names=["mel"],
                output_names=["embedding"],
                dynamic_axes={
                    "mel": {0: "batch_size", 2: "time"},
                    "embedding": {0: "batch_size"},
                },
                dynamo=False,
            )

            session = onnxruntime.InferenceSession(onnx_path)

            for time_len in [50, 100, 200, 400]:
                mel_np = np.random.randn(1, 80, time_len).astype(np.float32)
                result = session.run(["embedding"], {"mel": mel_np})[0]
                assert result.shape == (1, 32)

        finally:
            Path(onnx_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Evaluation utilities tests
# ---------------------------------------------------------------------------


class TestComputeEER:
    """Tests for EER computation."""

    def test_perfect_separation(self):
        """Perfect separation yields EER close to 0."""
        from piper_train.speaker_encoder.evaluate import compute_eer

        # Same-speaker pairs have score 0.9, different-speaker pairs 0.1
        labels = np.array([1, 1, 1, 0, 0, 0])
        scores = np.array([0.9, 0.85, 0.95, 0.1, 0.05, 0.15])
        eer, threshold = compute_eer(labels, scores)
        assert eer < 0.1  # Should be close to 0

    def test_random_scores(self):
        """EER for random scores is around 0.5."""
        from piper_train.speaker_encoder.evaluate import compute_eer

        np.random.seed(42)
        n = 500
        labels = np.concatenate([np.ones(n), np.zeros(n)]).astype(np.int32)
        scores = np.random.rand(n * 2)
        eer, _ = compute_eer(labels, scores)
        assert 0.3 < eer < 0.7  # Should be around 0.5

    def test_eer_range(self):
        """EER is in [0, 1]."""
        from piper_train.speaker_encoder.evaluate import compute_eer

        labels = np.array([1, 1, 0, 0])
        scores = np.array([0.8, 0.6, 0.4, 0.2])
        eer, threshold = compute_eer(labels, scores)
        assert 0.0 <= eer <= 1.0
        assert isinstance(threshold, float)


class TestLoadTestPairs:
    """Tests for test pairs file loading."""

    def test_load_valid_file(self):
        """Load a valid TSV pairs file."""
        from piper_train.speaker_encoder.evaluate import load_test_pairs

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("1\t/path/a.wav\t/path/b.wav\n")
            f.write("0\t/path/c.wav\t/path/d.wav\n")
            f.write("# comment line\n")
            f.write("\n")  # blank line
            f.write("1\t/path/e.wav\t/path/f.wav\n")
            pairs_path = f.name

        try:
            pairs = load_test_pairs(Path(pairs_path))
            assert len(pairs) == 3
            assert pairs[0] == (1, "/path/a.wav", "/path/b.wav")
            assert pairs[1] == (0, "/path/c.wav", "/path/d.wav")
            assert pairs[2] == (1, "/path/e.wav", "/path/f.wav")
        finally:
            Path(pairs_path).unlink(missing_ok=True)

    def test_missing_file(self):
        """Raise FileNotFoundError for missing file."""
        from piper_train.speaker_encoder.evaluate import load_test_pairs

        with pytest.raises(FileNotFoundError):
            load_test_pairs(Path("/nonexistent/pairs.txt"))

    def test_invalid_format(self):
        """Raise ValueError for malformed line."""
        from piper_train.speaker_encoder.evaluate import load_test_pairs

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("1\t/path/a.wav\n")  # only 2 fields
            pairs_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid format"):
                load_test_pairs(Path(pairs_path))
        finally:
            Path(pairs_path).unlink(missing_ok=True)

    def test_invalid_label(self):
        """Raise ValueError for label other than 0 or 1."""
        from piper_train.speaker_encoder.evaluate import load_test_pairs

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("2\t/path/a.wav\t/path/b.wav\n")
            pairs_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid label"):
                load_test_pairs(Path(pairs_path))
        finally:
            Path(pairs_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Sub-module tests (SEModule, Res2Net, ASP)
# ---------------------------------------------------------------------------


class TestSEModule:
    """Tests for the Squeeze-and-Excitation module."""

    def test_output_shape(self):
        from piper_train.speaker_encoder.ecapa_tdnn import SEModule

        se = SEModule(channels=64, bottleneck=16)
        x = torch.randn(2, 64, 100)
        out = se(x)
        assert out.shape == x.shape

    def test_recalibration_effect(self):
        """SE module modifies the input (not identity)."""
        from piper_train.speaker_encoder.ecapa_tdnn import SEModule

        se = SEModule(channels=64, bottleneck=16)
        x = torch.randn(1, 64, 50)
        out = se(x)
        assert not torch.allclose(x, out)


class TestRes2NetBlock:
    """Tests for the Res2Net block."""

    def test_output_shape(self):
        from piper_train.speaker_encoder.ecapa_tdnn import Res2NetBlock

        block = Res2NetBlock(channels=64, kernel_size=3, dilation=2, scale=8)
        x = torch.randn(2, 64, 100)
        out = block(x)
        assert out.shape == x.shape

    def test_channels_not_divisible(self):
        """Raise AssertionError when channels not divisible by scale."""
        from piper_train.speaker_encoder.ecapa_tdnn import Res2NetBlock

        with pytest.raises(AssertionError):
            Res2NetBlock(channels=65, kernel_size=3, dilation=2, scale=8)


class TestAttentiveStatisticsPooling:
    """Tests for Attentive Statistics Pooling."""

    def test_output_shape(self):
        from piper_train.speaker_encoder.ecapa_tdnn import AttentiveStatisticsPooling

        asp = AttentiveStatisticsPooling(channels=64, attention_channels=32)
        x = torch.randn(2, 64, 100)
        out = asp(x)
        assert out.shape == (2, 128)  # 2 * channels

    def test_variable_time(self):
        """ASP handles different time lengths."""
        from piper_train.speaker_encoder.ecapa_tdnn import AttentiveStatisticsPooling

        asp = AttentiveStatisticsPooling(channels=64, attention_channels=32)
        for t in [10, 50, 200]:
            x = torch.randn(1, 64, t)
            out = asp(x)
            assert out.shape == (1, 128)
