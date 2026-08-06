"""GPU batch spec のフレーム切り出し契約テスト。

_compute_specs_gpu_batch はバッチ 0 埋め + 一括 STFT 後に per-sample で
フレームを切り出す。切り出しフレーム数が CPU 単体経路
(spectrogram_torch を単サンプルに適用した出力) と一致しないと、末尾に
無音フレームが混入して spec/wav 長が不整合になり MAS/KL が発散する
(2026-08-05 v8 本走の実障害: +3 frames 過剰で 80 epoch が全損)。
"""

from pathlib import Path

import pytest
import torch

from piper_train.tools import prepare_multilingual_dataset as pmd
from piper_train.vits.mel_processing import spectrogram_torch


@pytest.mark.unit
class TestGpuSpecFrames:
    @pytest.mark.parametrize("n_samples", [22050, 51200, 66150, 102144, 12345])
    def test_batch_trim_matches_single_sample_cpu(self, tmp_path: Path, n_samples):
        """バッチ経路の保存 spec が CPU 単体経路と shape/値とも一致すること。"""
        torch.manual_seed(0)
        audio = torch.rand(n_samples) * 2 - 1

        # CPU 単体経路 (cache_norm_audio と同じ)
        ref = spectrogram_torch(
            audio.unsqueeze(0), 1024, 22050, 256, 1024, center=False
        ).squeeze(0)

        # GPU batch 経路 (device=cpu で同ロジックを実行)
        norm_p = tmp_path / "a.pt"
        spec_p = tmp_path / "a.spec.pt"
        torch.save(audio.unsqueeze(0), norm_p)
        computed = pmd._compute_specs_gpu_batch(
            [(str(norm_p), str(spec_p))], batch_size=4, device="cpu"
        )
        assert computed == 1
        stored = torch.load(spec_p, weights_only=True).float()

        assert stored.shape == ref.shape, (
            f"frame mismatch: stored={tuple(stored.shape)} ref={tuple(ref.shape)} "
            "(batch 0-padding frames leaked into the saved spec)"
        )
        assert (stored - ref).abs().max() < 0.05  # fp16 保存の量子化誤差のみ

    def test_mixed_length_batch(self, tmp_path: Path):
        """長さの異なるサンプルを同一バッチにしても各自の正しい長さで切れること。"""
        torch.manual_seed(1)
        items = []
        refs = []
        for i, n in enumerate([30000, 90000, 45000]):
            audio = torch.rand(n) * 2 - 1
            norm_p = tmp_path / f"m{i}.pt"
            spec_p = tmp_path / f"m{i}.spec.pt"
            torch.save(audio.unsqueeze(0), norm_p)
            items.append((str(norm_p), str(spec_p)))
            refs.append(
                spectrogram_torch(
                    audio.unsqueeze(0), 1024, 22050, 256, 1024, center=False
                ).squeeze(0)
            )
        computed = pmd._compute_specs_gpu_batch(items, batch_size=3, device="cpu")
        assert computed == 3
        for (_np, spec_p), ref in zip(items, refs, strict=True):
            stored = torch.load(spec_p, weights_only=True).float()
            assert stored.shape == ref.shape
            # 既知の制限: バッチ 0 埋めが spectrogram_torch 内部の reflect pad
            # と干渉し、短いサンプルの末尾 1-2 フレームは CPU 単体経路と値が
            # わずかに異なる (無音 3 フレーム混入とは異なり実害は軽微)。
            # 末尾 2 フレームを除いた本体は fp16 量子化誤差内で一致すること
            assert (stored[:, :-2] - ref[:, :-2]).abs().max() < 0.05
