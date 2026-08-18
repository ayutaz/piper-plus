"""S-2: dataset / collate の F0 配線と後方互換の TDD テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §4.6 の「配線」行。

固定する契約:

* **F0 キャッシュが無い dataset は従来どおり動く** (Batch.f0 / vuv が None)。
  S-2 は「キャッシュがある時だけ有効」であって、既存データセットの読み込みを
  壊さない。
* **フレーム数の不一致は例外**。F0 と spectrogram の時間ずれは聴感で気づけない
  ので、黙って合わせずに落とす。
* **padding フレームは f0=0 / vuv=0**。loss 側の frame mask と二重に無効化される。
* **``pin_memory()`` が新フィールドも拾う** (DataLoader の pin が無言で
  no-op に戻らない)。
"""

from __future__ import annotations

import json

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.dataset import (  # noqa: E402
    Batch,
    PiperDataset,
    UtteranceCollate,
    UtteranceTensors,
)


def _write_utterance(tmp_path, name: str, n_frames: int, with_f0: bool):
    spec = torch.randn(513, n_frames).abs()
    spec_path = tmp_path / f"{name}.spec.pt"
    torch.save(spec, spec_path)

    audio_path = tmp_path / f"{name}.npy"
    np.save(str(audio_path), np.zeros(n_frames * 256, dtype=np.float32))

    if with_f0:
        f0 = np.full(n_frames, 200.0, dtype=np.float16)
        f0[::4] = 0.0
        np.save(str(tmp_path / f"{name}.f0.npy"), f0)

    return {
        "phoneme_ids": [1, 2, 3],
        "audio_norm_path": str(audio_path),
        "audio_spec_path": str(spec_path),
        "speaker_id": 0,
    }


def _dataset_jsonl(tmp_path, records) -> str:
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) for r in records), encoding="utf-8"
    )
    return str(path)


def test_dataset_without_f0_cache_is_unchanged(tmp_path):
    records = [_write_utterance(tmp_path, "a", 40, with_f0=False)]
    ds = PiperDataset([_dataset_jsonl(tmp_path, records)])
    assert ds.utterances[0].f0_path is None
    assert ds[0].f0 is None


def test_dataset_resolves_f0_from_f0_dir(tmp_path):
    records = [_write_utterance(tmp_path, "a", 40, with_f0=True)]
    ds = PiperDataset([_dataset_jsonl(tmp_path, records)], f0_dir=tmp_path)
    assert ds.utterances[0].f0_path is not None
    item = ds[0]
    assert item.f0 is not None
    assert item.f0.shape == (40,)
    assert item.f0.dtype == torch.float32


def test_dataset_resolves_f0_from_jsonl_field(tmp_path):
    record = _write_utterance(tmp_path, "a", 40, with_f0=True)
    record["f0_path"] = str(tmp_path / "a.f0.npy")
    ds = PiperDataset([_dataset_jsonl(tmp_path, [record])])
    assert ds[0].f0 is not None


def test_missing_f0_file_falls_back_to_no_f0(tmp_path):
    """f0_dir を渡しても該当ファイルが無ければ「F0 なし」で読み込める。"""
    records = [_write_utterance(tmp_path, "a", 40, with_f0=False)]
    ds = PiperDataset([_dataset_jsonl(tmp_path, records)], f0_dir=tmp_path)
    assert ds[0].f0 is None


def test_nonexistent_f0_dir_is_tolerated(tmp_path):
    records = [_write_utterance(tmp_path, "a", 40, with_f0=False)]
    ds = PiperDataset(
        [_dataset_jsonl(tmp_path, records)], f0_dir=tmp_path / "does-not-exist"
    )
    assert ds.f0_dir is None
    assert ds[0].f0 is None


def test_frame_count_small_mismatch_is_padded(tmp_path):
    """±4 frame 以内の差は丸め差として端 pad/trim で吸収する。

    pyworld の frame_period (ms 単位 double) と STFT フレーム規約の丸め差は
    実データで最大 ±3 frame (v10b smoke arm S2 実測: 180 vs 183)。
    """
    records = [_write_utterance(tmp_path, "a", 40, with_f0=True)]
    np.save(str(tmp_path / "a.f0.npy"), np.full(37, 200.0, dtype=np.float16))
    ds = PiperDataset([_dataset_jsonl(tmp_path, records)], f0_dir=tmp_path)
    utt = ds[0]
    assert utt.f0 is not None
    assert utt.f0.shape[0] == utt.spectrogram.size(1) == 40
    # edge-pad: 末尾は最後の値の複製
    assert float(utt.f0[-1]) == pytest.approx(200.0)

    # 長すぎる側 (+3) は trim
    np.save(str(tmp_path / "a.f0.npy"), np.full(43, 200.0, dtype=np.float16))
    utt = ds[0]
    assert utt.f0.shape[0] == 40


def test_frame_count_large_mismatch_raises(tmp_path):
    """許容幅 (±4) を超える差は別 hop の無効キャッシュとして即エラー。"""
    records = [_write_utterance(tmp_path, "a", 40, with_f0=True)]
    np.save(str(tmp_path / "a.f0.npy"), np.zeros(30, dtype=np.float16))
    ds = PiperDataset([_dataset_jsonl(tmp_path, records)], f0_dir=tmp_path)
    with pytest.raises(ValueError, match="does not match spectrogram frames"):
        _ = ds[0]


# --------------------------------------------------------------------------
# collate
# --------------------------------------------------------------------------


def _utt(n_frames: int, f0_hz: float | None):
    f0 = None
    if f0_hz is not None:
        f0 = torch.full((n_frames,), f0_hz)
        f0[0] = 0.0  # 無声フレーム
    return UtteranceTensors(
        phoneme_ids=torch.LongTensor([1, 2, 3]),
        spectrogram=torch.randn(513, n_frames),
        audio_norm=torch.zeros(1, n_frames * 256),
        speaker_id=torch.LongTensor([0]),
        f0=f0,
    )


def test_collate_without_f0_leaves_batch_fields_none():
    batch = UtteranceCollate(is_multispeaker=True, segment_size=8192)(
        [_utt(30, None), _utt(20, None)]
    )
    assert batch.f0 is None
    assert batch.vuv is None


def test_collate_pads_f0_and_derives_vuv():
    batch = UtteranceCollate(is_multispeaker=True, segment_size=8192)(
        [_utt(30, 200.0), _utt(20, 150.0)]
    )
    assert batch.f0.shape == (2, 1, 30)
    assert batch.vuv.shape == (2, 1, 30)
    # collate は spec 長の降順に並べ替える → index 1 が短いほう
    assert torch.all(batch.f0[1, 0, 20:] == 0.0)
    assert torch.all(batch.vuv[1, 0, 20:] == 0.0)
    # V/UV は f0 > 0 と厳密に一致
    torch.testing.assert_close(batch.vuv, (batch.f0 > 0).float())


def test_collate_zero_fills_utterances_that_lack_f0():
    """一部の発話だけ F0 が欠けても落ちず、その行は無声扱いになる。"""
    batch = UtteranceCollate(is_multispeaker=True, segment_size=8192)(
        [_utt(30, 200.0), _utt(30, None)]
    )
    assert batch.f0 is not None
    assert float(batch.f0[1].abs().sum()) == 0.0


def test_pin_memory_carries_the_new_fields():
    batch = Batch(
        phoneme_ids=torch.zeros(1, 3, dtype=torch.long),
        phoneme_lengths=torch.zeros(1, dtype=torch.long),
        spectrograms=torch.zeros(1, 513, 4),
        spectrogram_lengths=torch.zeros(1, dtype=torch.long),
        audios=torch.zeros(1, 1, 1024),
        audio_lengths=torch.zeros(1, dtype=torch.long),
        f0=torch.zeros(1, 1, 4),
        vuv=torch.zeros(1, 1, 4),
    )
    pinned = batch.pin_memory()
    assert pinned.f0 is not None
    assert pinned.vuv is not None
    assert pinned.f0.shape == batch.f0.shape
