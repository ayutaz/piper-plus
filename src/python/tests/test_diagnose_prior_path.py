"""候補 A の事前診断 (next-direction S0、impl.md §6) の道具。

同じ発話を C の decoder のまま 4 通りの z で音にする:
posterior / MAS の並び + ns 0.4 / MAS の並び + ns 0 / 本来の推論 ns 0.4。
"""

from __future__ import annotations

import json

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")
pytest.importorskip("pytorch_lightning")

from piper_train.tools import diagnose_prior_path as dpp  # noqa: E402
from piper_train.tools.build_zs_eval_set import _check_spec  # noqa: E402


pytestmark = pytest.mark.unit

HOP = 256
SEG = 16 * HOP


def test_assign_roles_is_deterministic_and_disjoint():
    stems = [f"aaaa_{i:04d}" for i in range(30)]
    a = dpp.assign_roles(stems, seed=5, n_targets=10, n_cross=10)
    b = dpp.assign_roles(list(reversed(stems)), seed=5, n_targets=10, n_cross=10)
    assert a == b
    assert len(a["targets"]) == 10
    assert len(a["cross"]) == 10
    used = [a["reference"], *a["targets"], *a["cross"]]
    assert len(set(used)) == 21
    assert set(used) <= set(stems)


def test_assign_roles_refuses_a_speaker_with_too_few_utterances():
    with pytest.raises(ValueError, match="needs 21"):
        dpp.assign_roles(
            [f"a_{i}" for i in range(20)], seed=0, n_targets=10, n_cross=10
        )


def _row(stem, text="テスト"):
    return {
        "text": text,
        "phoneme_ids": [1, 0, 5, 0, 2],
        "prosody_features": [None, None, {"a1": 0, "a2": 1, "a3": 1}, None, None],
        "language_id": 0,
        "audio_path": f"/data/x/wavs/{stem}.wav",
    }


def _speaker(spk, n=3):
    stems = [f"{spk}_{i:04d}" for i in range(2 * n + 1)]
    return {
        "roles": {
            "reference": stems[0],
            "targets": stems[1 : n + 1],
            "cross": stems[n + 1 :],
        },
        "rows": {s: _row(s, text=f"文{s}") for s in stems},
        "sha256": {s: f"{i:064x}" for i, s in enumerate(stems)},
    }


def test_build_spec_puts_targets_in_clips_and_others_in_floor():
    speakers = {
        "aaaa": _speaker("aaaa"),
        "bbbb": _speaker("bbbb"),
        "cccc": _speaker("cccc"),
    }
    spec = dpp.build_spec(speakers, floor_per_speaker=2, name="diag")
    _check_spec(spec, {"moe-speech-plus": "unused"})
    group = spec["groups"]["ja_aaaa"]
    speaker_files = {f["file"] for f in group["files"] if f["role"] == "speaker"}
    floor_files = [f for f in group["files"] if f["role"] == "floor"]
    assert speaker_files == {
        f"{s}.wav" for s in ["aaaa_0000", "aaaa_0004", "aaaa_0005", "aaaa_0006"]
    }
    assert group["references"] == ["aaaa_0000.wav"]
    # 合成する発話の実録音は cross に入れない (同じ発話との比較を避ける)
    assert not speaker_files & {"aaaa_0001.wav", "aaaa_0002.wav", "aaaa_0003.wav"}
    assert len(floor_files) == 4
    assert {f["zip"] for f in floor_files} == {"bbbb.zip", "cccc.zip"}
    assert all(f["member"].startswith("data/") for f in group["files"])
    clips = [c for c in spec["clips"] if c["group"] == "ja_aaaa"]
    assert [c["id"] for c in clips] == [
        "ja_aaaa_aaaa_0001",
        "ja_aaaa_aaaa_0002",
        "ja_aaaa_aaaa_0003",
    ]
    assert clips[0]["text"] == "文aaaa_0001"
    assert clips[0]["phoneme_ids"] == [1, 0, 5, 0, 2]
    assert clips[0]["reference"] == 0
    assert clips[0]["prosody_features"][2] == {"a1": 0, "a2": 1, "a3": 1}


def test_residual_stats_pool_only_masked_frames():
    m_p = torch.zeros(1, 2, 4)
    logs_p = torch.log(torch.full((1, 2, 4), 2.0))
    z = torch.tensor([[[2.0, -2.0, 2.0, 99.0], [-2.0, 2.0, -2.0, 99.0]]])
    mask = torch.tensor([[[1.0, 1.0, 1.0, 0.0]]])
    stats = dpp.residual_stats(z, m_p, logs_p, mask)
    assert stats["count"] == 6
    assert stats["sum"] == pytest.approx(0.0)
    assert stats["sum_sq"] == pytest.approx(6.0)


def test_pool_residual_stats():
    pooled = dpp.pool_residual_stats(
        [
            {"count": 2, "sum": 2.0, "sum_sq": 4.0},
            {"count": 2, "sum": -2.0, "sum_sq": 4.0},
        ]
    )
    assert pooled["mean"] == pytest.approx(0.0)
    assert pooled["std"] == pytest.approx(np.sqrt(2.0))


def _tiny_checkpoint(tmp_path):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    model = VitsModel(
        num_symbols=20,
        num_speakers=4,
        num_languages=2,
        dataset=None,
        batch_size=2,
        use_wavlm_discriminator=False,
        use_zero_shot=True,
        use_snac_flow=True,
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
        upsample_initial_channel=32,
        resblock_kernel_sizes=(3,),
        resblock_dilation_sizes=((1, 2),),
        inter_channels=16,
        hidden_channels=16,
        filter_channels=32,
        n_layers=1,
        gin_channels=32,
        segment_size=SEG,
    )
    shadow = {n: p.detach() + 0.01 for n, p in model.model_g.dec.named_parameters()}
    ckpt = {
        "state_dict": model.state_dict(),
        "hyper_parameters": dict(model.hparams),
        "pytorch-lightning_version": "2.0.0",
        "epoch": 39,
        "ema_generator_state": {
            "decay": 0.9995,
            "num_updates": 1,
            "shadow_params": shadow,
        },
    }
    path = tmp_path / "base.ckpt"
    torch.save(ckpt, path)
    return path


def _mini_set(tmp_path):
    import soundfile as sf

    root = tmp_path / "set"
    group = root / "groups" / "ja_aaaa"
    group.mkdir(parents=True)
    np.save(group / "ref0.npy", np.ones(192, dtype=np.float32) / np.sqrt(192))
    rows, targets = [], []
    t = np.arange(int(22050 * 1.2)) / 22050
    for i in range(2):
        clip_id = f"ja_aaaa_aaaa_{i:04d}"
        wav = (0.3 * np.sin(2 * np.pi * (180 + 20 * i) * t)).astype(np.float32)
        path = root / "targets" / "ja_aaaa" / f"{clip_id}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, wav, 22050, subtype="PCM_16")
        rows.append(
            {
                "id": clip_id,
                "text": "テスト",
                "phoneme_ids": [1, 0, 5, 0, 7, 0, 2],
                "language_id": 0,
                "speaker_id": 0,
                "speaker_embedding_path": "groups/ja_aaaa/ref0.npy",
                "prosody_features": [None] * 7,
            }
        )
        targets.append(
            {
                "id": clip_id,
                "file": f"targets/ja_aaaa/{clip_id}.wav",
                "sha256": dpp._sha256(path),
            }
        )
    (root / "test.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (root / "targets.json").write_text(
        json.dumps({"targets": targets}), encoding="utf-8"
    )
    return root


def test_generate_writes_the_four_paths_for_run_zs_eval_set(tmp_path):
    ckpt = _tiny_checkpoint(tmp_path)
    set_dir = _mini_set(tmp_path)
    out = tmp_path / "out"
    record = dpp.generate(ckpt, set_dir, out, seed=42, device="cpu")
    import soundfile as sf

    assert set(record["paths"]) == set(dpp.PATHS)
    for name in dpp.PATHS:
        generation = json.loads((out / name / "generation.json").read_text("utf-8"))
        assert generation["backend"] == "torch-ema"
        assert generation["seed"] == 42
        assert generation["z_path"] == name
        ids = [c["id"] for c in generation["clips"]]
        assert ids == ["ja_aaaa_aaaa_0000", "ja_aaaa_aaaa_0001"]
        for clip in generation["clips"]:
            wav = out / name / f"{clip['id']}.wav"
            assert dpp._sha256(wav) == clip["wav_sha256"]
    # MAS で並べた経路は実録音と同じフレーム数、本来の推論は継続長予測で決まる
    post, _ = sf.read(out / "posterior" / "ja_aaaa_aaaa_0000.wav")
    ns04, _ = sf.read(out / "prior-ns0.4" / "ja_aaaa_aaaa_0000.wav")
    ns0, _ = sf.read(out / "prior-ns0" / "ja_aaaa_aaaa_0000.wav")
    assert len(post) == len(ns04) == len(ns0)
    assert len(post) % HOP == 0
    assert not np.allclose(ns04, ns0)
    stats = json.loads((out / "latent_stats.json").read_text("utf-8"))
    assert stats["pooled"]["count"] > 0
    assert set(stats["clips"]) == {"ja_aaaa_aaaa_0000", "ja_aaaa_aaaa_0001"}


def test_generate_is_reproducible(tmp_path):
    ckpt = _tiny_checkpoint(tmp_path)
    set_dir = _mini_set(tmp_path)
    import soundfile as sf

    a = dpp.generate(ckpt, set_dir, tmp_path / "a", seed=42, device="cpu")
    b = dpp.generate(ckpt, set_dir, tmp_path / "b", seed=42, device="cpu")
    # float WAV の PEAK chunk は書いた時刻を持つので、file の hash ではなく音で比べる
    for name in dpp.PATHS:
        for clip in a["paths"][name]:
            wa, _ = sf.read(tmp_path / "a" / name / f"{clip['id']}.wav")
            wb, _ = sf.read(tmp_path / "b" / name / f"{clip['id']}.wav")
            np.testing.assert_array_equal(wa, wb)
    assert a["latent_stats"] == b["latent_stats"]


def test_generate_refuses_a_changed_target_recording(tmp_path):
    ckpt = _tiny_checkpoint(tmp_path)
    set_dir = _mini_set(tmp_path)
    target = set_dir / "targets" / "ja_aaaa" / "ja_aaaa_aaaa_0001.wav"
    target.write_bytes(target.read_bytes()[:-2] + b"\x01\x01")
    with pytest.raises(ValueError, match="sha256"):
        dpp.generate(ckpt, set_dir, tmp_path / "out", seed=42, device="cpu")


def test_generate_refuses_a_non_empty_output(tmp_path):
    ckpt = _tiny_checkpoint(tmp_path)
    set_dir = _mini_set(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "x").write_text("x")
    with pytest.raises(ValueError, match="not empty"):
        dpp.generate(ckpt, set_dir, out, seed=42, device="cpu")
