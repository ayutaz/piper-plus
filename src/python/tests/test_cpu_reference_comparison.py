"""Control reference duration and keep source utterances out of evaluation."""

import numpy as np
import pytest


def test_crop_matches_active_frames_without_removing_internal_pauses():
    from piper_train.tools.cpu_reference_comparison import crop_active_frames

    # Five active frames separated by silence; preserve the internal silence.
    audio = np.repeat([0, 1, 1, 0, 1, 1, 1, 0], 320).astype(np.float32)
    crop, metadata = crop_active_frames(audio, 16000, 3)
    assert metadata["active_frames"] == 3
    assert metadata["start_frame"] == 1
    assert metadata["end_frame"] == 5
    np.testing.assert_array_equal(crop, audio[320:1600])


def test_activity_crop_rejects_silence_insufficient_and_nonfinite():
    from piper_train.tools.cpu_reference_comparison import crop_active_frames

    for audio in (np.zeros(1600), np.ones(320), np.full(1600, np.nan)):
        with pytest.raises(ValueError):
            crop_active_frames(audio, 16000, 2)


def test_exclusion_covers_source_utterances_and_content_aliases(tmp_path):
    from piper_train.tools.cpu_reference_comparison import independent_reals

    original = tmp_path / "original.wav"
    alias = tmp_path / "alias.wav"
    crop = tmp_path / "crop.wav"
    real = tmp_path / "real.wav"
    original.write_bytes(b"source")
    alias.write_bytes(b"source")
    crop.write_bytes(b"cropped")
    real.write_bytes(b"independent")
    assert independent_reals([original, alias, crop, real], [original, crop]) == [real]


def test_exclusion_never_accepts_empty_source_list(tmp_path):
    from piper_train.tools.cpu_reference_comparison import independent_reals

    with pytest.raises(ValueError, match="sources"):
        independent_reals([tmp_path / "anything.wav"], [])


def test_native_speechbrain_singleton_output_is_a_unit_vector(tmp_path):
    import soundfile as sf
    import torch

    from piper_train.tools.cpu_reference_comparison import native_ecapa_embedding

    class Classifier:
        def encode_batch(self, waveform):
            assert waveform.shape == (1, 16000)
            return torch.ones(1, 1, 192)

    wav = tmp_path / "real.wav"
    sf.write(wav, np.ones(16000, dtype=np.float32) * 0.1, 16000)
    vector = native_ecapa_embedding(Classifier(), wav)
    assert vector.shape == (192,)
    assert np.linalg.norm(vector) == pytest.approx(1.0)


class _MeanFbankSession:
    """CAM++ ONNX の代役: fbank の時間平均を 192 次元へ並べて返す決定的 session。"""

    class _Input:
        name = "feats"

    def get_inputs(self):
        return [self._Input()]

    def run(self, _outputs, feeds):
        fbank = feeds["feats"][0]
        summary = np.concatenate([fbank.mean(axis=0), fbank.std(axis=0)])
        return [np.resize(summary, 192)[None, :] + 1e-3]


def test_reference_embedding_trim_changes_only_with_silence(tmp_path):
    import soundfile as sf

    from piper_train.tools.cpu_reference_comparison import reference_embedding

    rng = np.random.default_rng(0)
    # 16 kHz・480 sample の倍数長・全区間が VAD 閾値 (RMS 0.02) を大きく超える
    voiced = (0.3 * rng.standard_normal(480 * 50)).astype(np.float32)
    loud = tmp_path / "loud.wav"
    sf.write(loud, voiced, 16000, subtype="FLOAT")
    session = _MeanFbankSession()
    plain, _ = reference_embedding(session, [loud])
    trimmed, _ = reference_embedding(session, [loud], trim=True)
    np.testing.assert_array_equal(plain, trimmed)

    # 前後に無音を付けると trim の有無で fbank の CMN 平均が変わり、出力も変わる
    silence = np.zeros(16000, dtype=np.float32)
    padded = tmp_path / "padded.wav"
    sf.write(padded, np.concatenate([silence, voiced, silence]), 16000, subtype="FLOAT")
    padded_plain, _ = reference_embedding(session, [padded])
    padded_trimmed, _ = reference_embedding(session, [padded], trim=True)
    assert not np.allclose(padded_plain, padded_trimmed)
    # trim 後は (VAD の keep_before/after 2 chunk を除き) 無音なし版へ近づく
    assert float(padded_trimmed @ plain) > float(padded_plain @ plain)


def test_projected_average_equals_single_when_one_reference():
    import torch

    from piper_train.tools.cpu_reference_comparison import projected_average

    torch.manual_seed(0)
    model = torch.nn.Module()
    model.spk_proj = torch.nn.Sequential(
        torch.nn.Linear(192, 16),
        torch.nn.LayerNorm(16),
        torch.nn.GELU(),
        torch.nn.Linear(16, 16),
    )
    embeddings = np.random.default_rng(1).standard_normal((2, 192)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    with torch.no_grad():
        single = projected_average(model, embeddings[:1])
        expected = model.spk_proj(torch.from_numpy(embeddings[:1]))
        assert single.shape == (1, 16)
        torch.testing.assert_close(single, expected)
        # 2 参照は g 側 (spk_proj 出力) の平均であり、埋め込み平均の射影ではない
        both = projected_average(model, embeddings)
        projected = model.spk_proj(torch.from_numpy(embeddings))
        torch.testing.assert_close(both, projected.mean(dim=0, keepdim=True))
    with pytest.raises(ValueError):
        projected_average(model, np.zeros((0, 192), dtype=np.float32))
    with pytest.raises(ValueError):
        projected_average(model, np.full((1, 192), np.nan, dtype=np.float32))


def test_pairwise_separability_counts_pairs_and_auc():
    from piper_train.tools.cpu_reference_comparison import pairwise_separability

    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9], [0.7, 0.7]])
    labels = ["a", "a", "b", "b", "c"]
    result = pairwise_separability(vectors, labels)
    assert result["n_speakers"] == 3
    assert result["n_utterances"] == 5
    assert result["n_same_pairs"] == 2
    assert result["n_other_pairs"] == 8
    # 同話者 2 対はどの別話者対よりも cosine が大きい
    assert result["auc"] == pytest.approx(1.0)
    assert result["gap"] == pytest.approx(result["same_mean"] - result["other_mean"])
    # 同話者対が別話者対と完全に同順位なら AUC=0.5 (同値は 0.5 として数える)
    tied = pairwise_separability(np.ones((4, 2)), ["a", "a", "b", "b"])
    assert tied["auc"] == pytest.approx(0.5)
    # 次元ごとの標準化 (同じ pooled 集合で平均 0・分散 1) を任意で適用
    standardized = pairwise_separability(vectors + 5.0, labels, standardize=True)
    assert standardized["normalization"].startswith("per-dimension z-score")
    with pytest.raises(ValueError):
        pairwise_separability(vectors[:2], ["a", "a"])
