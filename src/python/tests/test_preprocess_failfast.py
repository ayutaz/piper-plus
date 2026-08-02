"""前処理パイプラインの fail-fast 契約テスト。

2026-08-01/02 の v8 dataset 再構築で、環境起因の全滅が exit 0 の
「静かな成功」として通過し、ja のみ 54k のデータセットが完成扱いに
なった実障害の再発防止。pin する契約:

1. `prepare_multilingual_dataset.process_new_language`
   - 指定ソースが 0 件 parse → RuntimeError (ES train.csv 欠落の再発防止)
   - 音素化成功率 <50% → RuntimeError (旧 g2p の ko inventory 欠落の再発防止)
   - assemble 成功率 <50% → RuntimeError (.npy cache 読めず全滅の再発防止)
2. `prepare_bilingual_dataset.process_en_dataset`
   - 音素化成功率 <50% → RuntimeError (NLTK data 未 DL の再発防止)
   - worker エラーメッセージに例外型名を含む (空メッセージ化の再発防止)
3. `extract_speaker_embedding.extract_per_utterance`
   - 全 entry 失敗 → RuntimeError (jsonl へ実在しない emb path を書かない)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from piper_train.tools import (
    prepare_bilingual_dataset as pbd,
    prepare_multilingual_dataset as pmd,
)


# 最小の有効な id_map (^/$/_ + 数個の音素)
_ID_MAP = {"^": [1], "$": [2], "_": [0], "a": [4], "b": [5], "?": [3]}


@pytest.mark.unit
class TestProcessNewLanguageFailFast:
    def test_zero_parsed_entries_raises(self, tmp_path: Path):
        """指定ソースが 0 件 parse なら silent skip せず RuntimeError。"""
        with pytest.raises(RuntimeError, match="no ES utterances were parsed"):
            pmd.process_new_language(
                entries=[],
                speaker_counts={},
                language="es",
                language_id=3,
                speaker_id_offset=0,
                ml_id_map=_ID_MAP,
                cache_dir=tmp_path,
                sample_rate=22050,
                workers=1,
            )

    def test_low_phonemize_rate_raises(self, tmp_path: Path, monkeypatch):
        """音素化成功率 <50% (環境起因の全滅) は RuntimeError。"""
        entries = [(f"text {i}", f"/nonexistent/{i}.wav", "spk1") for i in range(10)]

        monkeypatch.setattr(
            pmd,
            "phonemize_new_language",
            lambda *a, **k: ([{"text": "text 0"}], {}),  # 1/10 成功
        )
        with pytest.raises(RuntimeError, match="KO phonemization succeeded for only"):
            pmd.process_new_language(
                entries=entries,
                speaker_counts={"spk1": 10},
                language="ko",
                language_id=7,
                speaker_id_offset=0,
                ml_id_map=_ID_MAP,
                cache_dir=tmp_path,
                sample_rate=22050,
                workers=1,
            )

    def test_low_assemble_rate_raises(self, tmp_path: Path, monkeypatch):
        """音素化は成功したのに assemble 全滅 (cache 形式不整合) は RuntimeError。"""
        entries = [(f"text {i}", f"/nonexistent/{i}.wav", "spk1") for i in range(4)]
        phonemized = [
            {
                "text": f"text {i}",
                "wav_path": f"/nonexistent/{i}.wav",
                "speaker": "spk1",
                "phoneme_ids": [1, 4, 2],
                "prosody_features": [None, None, None],
            }
            for i in range(4)
        ]
        monkeypatch.setattr(
            pmd, "phonemize_new_language", lambda *a, **k: (phonemized, {})
        )
        # audio cache 全滅 (audio_map 空 → assemble 0 件)
        monkeypatch.setattr(pmd, "cache_audio_parallel", lambda *a, **k: {})
        with pytest.raises(RuntimeError, match="ZH assembled only 0/4"):
            pmd.process_new_language(
                entries=entries,
                speaker_counts={"spk1": 4},
                language="zh",
                language_id=2,
                speaker_id_offset=0,
                ml_id_map=_ID_MAP,
                cache_dir=tmp_path,
                sample_rate=22050,
                workers=1,
            )


@pytest.mark.unit
class TestProcessEnDatasetFailFast:
    def _make_en_dir(self, root: Path, n: int = 4) -> Path:
        en = root / "en-ljspeech"
        (en / "wavs").mkdir(parents=True)
        rows = []
        for i in range(n):
            (en / "wavs" / f"utt{i}.wav").write_bytes(b"RIFF fake")
            rows.append(f"utt{i}|spk{i % 2}|hello world number {i}")
        (en / "metadata.csv").write_text("\n".join(rows), encoding="utf-8")
        return en

    def test_all_phonemize_failures_raise(self, tmp_path: Path, monkeypatch):
        """全発話が音素化失敗 (例: NLTK data 欠落) なら RuntimeError。

        workers=1 の serial 経路で phonemizer を fail させる (ProcessPool の
        pickling を避けつつ、成功率 gate は経路共通のため契約は等価)。
        """
        en_dir = self._make_en_dir(tmp_path)
        monkeypatch.setattr(
            pbd, "MultilingualPhonemizer", lambda langs: _RaisingPhonemizer()
        )
        with pytest.raises(RuntimeError, match="environment problem"):
            pbd.process_en_dataset(
                en_input_dir=en_dir,
                bilingual_id_map=_ID_MAP,
                sample_rate=22050,
                cache_dir=tmp_path / "cache",
                en_speaker_id_offset=100,
                workers=1,
                min_utterances_per_speaker=0,
            )

    def test_worker_error_message_includes_exception_type(self):
        """worker のエラーメッセージは例外型名を含む (空メッセージ防止)。

        NLTK LookupError は str(e) が改行始まりでログ上「空」に見えた。
        """
        pbd._phonemize_worker_state["phonemizer"] = _RaisingPhonemizer()
        pbd._phonemize_worker_state["id_map"] = _ID_MAP
        try:
            result = pbd._phonemize_en_worker(("f.wav", "text", "/tmp/f.wav", 0))
        finally:
            pbd._phonemize_worker_state.clear()
        assert "error" in result
        assert result["error"].startswith("LookupError:"), result["error"]


class _RaisingPhonemizer:
    def phonemize_with_prosody(self, text):
        raise LookupError("\n****\n  Resource not found.\n****\n")


@pytest.mark.unit
class TestExtractEmbeddingFailFast:
    def test_all_failures_raise_and_do_not_touch_jsonl(self, tmp_path: Path):
        """CAM++ 抽出が全滅したら RuntimeError、dataset.jsonl は書き換えない。"""
        from piper_train import extract_speaker_embedding as ese

        ds = tmp_path / "ds"
        cache = ds / "cache" / "22050"
        cache.mkdir(parents=True)
        entries = []
        for i in range(3):
            # 壊れた audio_norm cache (読み込み必ず失敗)
            p = cache / f"utt{i}.pt"
            p.write_bytes(b"not a torch file")
            entries.append({"audio_norm_path": str(p), "speaker": "s", "speaker_id": 0})
        jsonl = ds / "dataset.jsonl"
        original = "".join(json.dumps(e) + "\n" for e in entries)
        jsonl.write_text(original, encoding="utf-8")
        (ds / "config.json").write_text('{"audio": {"sample_rate": 22050}}')

        class _FakeSession:
            def get_providers(self):
                return ["CPUExecutionProvider"]

            def get_inputs(self):
                class _I:
                    name = "fbank"

                return [_I()]

            def get_outputs(self):
                class _O:
                    name = "embedding"

                return [_O()]

            def run(self, *_a, **_k):
                return [np.zeros((1, 192), dtype=np.float32)]

        with pytest.raises(RuntimeError, match="failed for all 3 entries"):
            ese.extract_per_utterance(
                session=_FakeSession(),
                dataset_dir=ds,
                source_sr=22050,
                batch_size=2,
                num_workers=0,
                fixed_frames=0,
            )
        # jsonl は無傷 (存在しない emb path を書き込まない)
        assert jsonl.read_text(encoding="utf-8") == original


@pytest.mark.unit
class TestAudioNormSharedLoader:
    def test_no_direct_torch_load_on_audio_norm_readers(self):
        """audio_norm cache を読むツールは共有ローダー経由であること (静的契約)。

        T-npy 切替 (write 側 .npy 化) 後に直接 torch.load するリーダーが
        残っていると、新規 cache を読めず全滅する (2026-08-01 実障害)。
        """
        import inspect

        from piper_train import extract_speaker_embedding as ese
        from piper_train.tools import batch_spectrograms as bs
        from piper_train.tools import prepare_multilingual_dataset as pmd_mod

        # audio_norm cache path を指す変数名の既知パターン。torch.load の
        # 引数にこれらが現れたら共有ローダー経由に置き換えること
        # (norm_p は 2026-08-02 に grep 網をすり抜けた実例)
        cache_var_markers = ("pt_path", "norm_p", "norm_path", "audio_norm")
        for mod in (ese, bs, pmd_mod):
            src = inspect.getsource(mod)
            for lineno, line in enumerate(src.splitlines(), 1):
                stripped = line.split("#")[0]
                if "torch.load(" in stripped:
                    hit = [m for m in cache_var_markers if m in stripped]
                    assert not hit, (
                        f"{mod.__name__}:{lineno} loads audio_norm cache with "
                        f"torch.load directly (matched {hit}); use "
                        f"piper_train.norm_audio.load_audio_norm_tensor: {line}"
                    )

    def test_num_languages_covers_max_language_id(self):
        """config の num_languages は max(language_id)+1 であること (静的契約)。

        extended map は sv=6 を予約欠番にして ko=7 を割り当てるため、
        7-lang (ja..pt + ko) では num_languages=8 が必要。len(languages)=7
        だと emb_lang(7) に language_id=7 が入り CUDA device-side assert で
        学習が即死する (2026-08-02 v8 smoke の実障害)。
        """
        import inspect

        src = inspect.getsource(pmd.main)
        assert '"num_languages": max(config_language_id_map.values()) + 1' in src, (
            "prepare_multilingual_dataset の num_languages は "
            "max(language_id)+1 で計算すること (len(active_languages) は "
            "sv=6 欠番のため ko=7 を範囲外にする)"
        )

    def test_shared_loader_reads_both_formats(self, tmp_path: Path):
        from piper_train.norm_audio import load_audio_norm_tensor

        t = torch.rand(128)
        pt = tmp_path / "a.pt"
        torch.save(t, pt)
        npy = tmp_path / "b.npy"
        np.save(npy, t.numpy())

        assert torch.equal(load_audio_norm_tensor(pt), t)
        assert torch.equal(load_audio_norm_tensor(npy), t)
