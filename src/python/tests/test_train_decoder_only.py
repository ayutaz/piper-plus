"""Decoder-only training for the P1 decoder comparison (design §5)."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")
pytest.importorskip("pytorch_lightning")

from torch.nn import functional as F  # noqa: E402


pytestmark = pytest.mark.unit

HOP = 256
SEG = 16 * HOP


def _tiny_checkpoint(tmp_path, **overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    model = VitsModel(
        **{
            **_TINY,
            **overrides,
        }
    )
    shadow = {n: p.detach() + 0.5 for n, p in model.model_g.dec.named_parameters()}
    ckpt = {
        "state_dict": model.state_dict(),
        "hyper_parameters": dict(model.hparams),
        "pytorch-lightning_version": "2.0.0",
        "ema_generator_state": {
            "decay": 0.9995,
            "num_updates": 1,
            "shadow_params": shadow,
        },
    }
    path = tmp_path / "base.ckpt"
    torch.save(ckpt, path)
    return path, ckpt


_TINY = {
    "num_symbols": 20,
    "num_speakers": 4,
    "num_languages": 2,
    "dataset": None,
    "batch_size": 2,
    "use_wavlm_discriminator": False,
    "use_zero_shot": True,
    "use_mrd": True,
    "use_jcu_mrd": True,
    "trainable_pqmf_synthesis": True,
    "upsample_rates": (4, 4),
    "upsample_kernel_sizes": (16, 16),
    "upsample_initial_channel": 32,
    "resblock_kernel_sizes": (3,),
    "resblock_dilation_sizes": ((1, 2),),
    "inter_channels": 16,
    "hidden_channels": 16,
    "filter_channels": 32,
    "n_layers": 1,
    "gin_channels": 32,
    "segment_size": SEG,
}


def _batch(n=2, frames=40):
    torch.manual_seed(3)
    audio = torch.randn(n, frames * HOP) * 0.1
    return {
        "audio": audio,
        "audio_lengths": torch.full((n,), frames * HOP),
        "speaker_embeddings": F.normalize(torch.randn(n, 192), dim=-1),
        "language_ids": torch.zeros(n, dtype=torch.long),
    }


def test_candidates_cover_the_design_table():
    from piper_train.tools.train_decoder_only import CANDIDATES

    assert {"d0", "d1", "d2-32", "d2-64", "d4", "d5"} <= set(CANDIDATES)
    assert CANDIDATES["d0"].init == "v10b" and CANDIDATES["d1"].init == "scratch"
    assert CANDIDATES["d0"].variant == CANDIDATES["d1"].variant


def test_v10b_init_takes_ema_decoder_and_fixes_pqmf(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import CANDIDATES, build_models

    path, ckpt = _tiny_checkpoint(tmp_path)
    models = build_models(load_checkpoint(path), CANDIDATES["d0"])
    dec = models.model_g.dec
    name, shadow = next(iter(ckpt["ema_generator_state"]["shadow_params"].items()))
    torch.testing.assert_close(dict(dec.named_parameters())[name], shadow)
    assert not any(p.requires_grad for p in dec.pqmf.parameters())
    assert dec.pqmf is models.pqmf  # one bank for synthesis and the sub-band target
    # discriminators come from the checkpoint
    w = next(iter(models.model_d.state_dict()))
    torch.testing.assert_close(
        models.model_d.state_dict()[w], ckpt["state_dict"][f"model_d.{w}"]
    )


def test_scratch_init_keeps_random_decoder_and_discriminators(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import CANDIDATES, build_models

    path, ckpt = _tiny_checkpoint(tmp_path)
    models = build_models(load_checkpoint(path), CANDIDATES["d1"])
    name, shadow = next(iter(ckpt["ema_generator_state"]["shadow_params"].items()))
    assert not torch.allclose(dict(models.model_g.dec.named_parameters())[name], shadow)
    w = next(iter(models.model_d.state_dict()))
    assert not torch.allclose(
        models.model_d.state_dict()[w], ckpt["state_dict"][f"model_d.{w}"]
    )
    # the frozen parts still come from the checkpoint
    q = next(iter(models.model_g.enc_q.state_dict()))
    torch.testing.assert_close(
        models.model_g.enc_q.state_dict()[q], ckpt["state_dict"][f"model_g.enc_q.{q}"]
    )


def test_wider_output_layer_keeps_the_rest_of_the_v10b_decoder(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import CANDIDATES, build_models

    path, ckpt = _tiny_checkpoint(tmp_path)
    models = build_models(load_checkpoint(path), CANDIDATES["d2-32"])
    dec = models.model_g.dec
    assert dec.n_fft == 32
    shadow = ckpt["ema_generator_state"]["shadow_params"]
    loaded = [
        n
        for n, p in dec.named_parameters()
        if n in shadow and p.shape == shadow[n].shape and torch.equal(p, shadow[n])
    ]
    assert any(n.startswith("ups.") or n.startswith("resblocks.") for n in loaded)
    assert dec.pqmf is models.pqmf


def test_train_step_updates_only_decoder_and_discriminators(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import (
        CANDIDATES,
        DecoderTrainer,
        TrainConfig,
        build_models,
    )

    path, _ = _tiny_checkpoint(tmp_path)
    models = build_models(load_checkpoint(path), CANDIDATES["d0"])
    trainer = DecoderTrainer(
        models, TrainConfig(segment_frames=16, band_disc_ffts=(256, 128)), device="cpu"
    )
    enc_q = {k: v.clone() for k, v in models.model_g.enc_q.state_dict().items()}
    spk = {k: v.clone() for k, v in models.model_g.spk_proj.state_dict().items()}
    dec = {k: v.clone() for k, v in models.model_g.dec.state_dict().items()}
    logs = trainer.step(_batch())
    for key in (
        "loss_mel",
        "loss_disc_all",
        "loss_gen_bmrd",
        "loss_gen_mrd",
        "loss_sub_stft",
    ):
        assert np.isfinite(logs[key]), key
    for k, v in models.model_g.enc_q.state_dict().items():
        torch.testing.assert_close(v, enc_q[k])
    for k, v in models.model_g.spk_proj.state_dict().items():
        torch.testing.assert_close(v, spk[k])
    assert any(
        not torch.equal(v, dec[k]) for k, v in models.model_g.dec.state_dict().items()
    )
    assert trainer.global_step == 1


def test_save_and_resume_round_trip(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import (
        CANDIDATES,
        DecoderTrainer,
        TrainConfig,
        build_models,
    )

    path, _ = _tiny_checkpoint(tmp_path)
    cfg = TrainConfig(segment_frames=16, band_disc_ffts=(256, 128))
    a = DecoderTrainer(
        build_models(load_checkpoint(path), CANDIDATES["d0"]), cfg, device="cpu"
    )
    a.step(_batch())
    run = tmp_path / "run.pt"
    a.save(run, candidate="d0")
    b = DecoderTrainer(
        build_models(load_checkpoint(path), CANDIDATES["d0"]), cfg, device="cpu"
    )
    b.load(run)
    assert b.global_step == 1
    for (k, v), (_, w) in zip(
        a.models.model_g.dec.state_dict().items(),
        b.models.model_g.dec.state_dict().items(),
        strict=True,
    ):
        torch.testing.assert_close(v, w, msg=k)
    for (k, v), (_, w) in zip(
        a.ema.state_dict().items(), b.ema.state_dict().items(), strict=True
    ):
        torch.testing.assert_close(v, w, msg=k)
    la, lb = a.step(_batch()), b.step(_batch())
    assert la["loss_mel"] == pytest.approx(lb["loss_mel"], rel=1e-5)


def test_trained_generator_uses_the_ema_decoder(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import (
        CANDIDATES,
        DecoderTrainer,
        TrainConfig,
        build_models,
        load_trained_generator,
    )

    path, _ = _tiny_checkpoint(tmp_path)
    t = DecoderTrainer(
        build_models(load_checkpoint(path), CANDIDATES["d0"]),
        TrainConfig(segment_frames=16, band_disc_ffts=(256, 128)),
        device="cpu",
    )
    t.step(_batch())
    run = tmp_path / "run.pt"
    t.save(run, candidate="d0")
    g = load_trained_generator(path, run, device="cpu")
    ema = t.ema.state_dict()
    for k, v in g.dec.state_dict().items():
        torch.testing.assert_close(v, ema[k], msg=k)


def _trained_run(tmp_path, candidate="d0"):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import (
        CANDIDATES,
        DecoderTrainer,
        TrainConfig,
        build_models,
    )

    path, ckpt = _tiny_checkpoint(tmp_path)
    # a small EMA offset: the +0.5 of the fixture makes the tiny decoder diverge
    shadow = ckpt["ema_generator_state"]["shadow_params"]
    ckpt["ema_generator_state"]["shadow_params"] = {
        n: v - 0.5 + 0.01 for n, v in shadow.items()
    }
    torch.save(ckpt, path)
    t = DecoderTrainer(
        build_models(load_checkpoint(path), CANDIDATES[candidate]),
        TrainConfig(segment_frames=16, band_disc_ffts=(256, 128)),
        device="cpu",
    )
    t.step(_batch())
    run = tmp_path / "run.pt"
    t.save(run, candidate=candidate)
    return path, run


def _synthesis_manifest(tmp_path, base):
    from piper_train.evaluation_manifest import create_manifest

    np.save(tmp_path / "ref.npy", np.full(192, 192**-0.5, dtype=np.float32))
    (tmp_path / "ref.wav").write_bytes(b"ref")
    rows = [
        {
            "id": f"c{i}",
            "text": text,
            "phoneme_ids": [1] + [5, 6, 7] * 4 + [2],
            "language_id": 0,
            "speaker_embedding_path": "ref.npy",
            "reference_audio_paths": ["ref.wav"],
        }
        for i, text in enumerate(["あ", "い"])
    ]
    source = tmp_path / "test.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    create_manifest(
        source_path=source,
        output_path=manifest,
        models={"torch-raw": base, "torch-ema": base},
        sample_rate=22050,
        asr_revision="a" * 40,
        source_revision="b" * 40,
    )
    return manifest


def test_synthesis_with_a_trained_decoder_matches_the_trained_generator(tmp_path):
    """P2 前の確認: v10b の合成経路の decoder だけを P1 の decoder に替える。"""
    from piper_train.embedding_cache import file_sha256
    from piper_train.inference_eval import isolated_inference
    from piper_train.tools import generate_eval_audio as generation
    from piper_train.tools.train_decoder_only import load_trained_generator
    from piper_train.vits.wavfile import read

    base, run = _trained_run(tmp_path)
    manifest = _synthesis_manifest(tmp_path, base)
    out = tmp_path / "swap"
    report = generation.generate_audio(
        manifest, "torch-ema", out, device="cpu", decoder_run=run
    )
    assert report["decoder_run"] == {
        "path": str(run),
        "sha256": file_sha256(run),
        "candidate": "d0",
        "global_step": 1,
    }
    expected = load_trained_generator(base, run, device="cpu")
    clips = json.loads(manifest.read_text(encoding="utf-8"))["clips"]
    for ordinal, clip in enumerate(clips):
        with isolated_inference(expected, 42 + ordinal):
            audio = expected.infer(
                torch.tensor([clip["phoneme_ids"]]),
                torch.tensor([len(clip["phoneme_ids"])]),
                speaker_embeddings=torch.from_numpy(
                    np.load(tmp_path / "ref.npy")[None]
                ),
                lid=torch.tensor([0]),
                sid=torch.tensor([clip["speaker_id"]]),
                noise_scale=0.4,
                length_scale=1.0,
                noise_scale_w=0.5,
            )[0]
        _, wav = read(out / f"{clip['id']}.wav")
        np.testing.assert_allclose(wav, audio.numpy().reshape(-1), atol=1e-6)
    plain = generation.generate_audio(manifest, "torch-ema", tmp_path / "plain")
    assert "decoder_run" not in plain
    assert plain["clips"][0]["wav_sha256"] != report["clips"][0]["wav_sha256"]


def test_trained_decoder_is_only_for_the_ema_backend(tmp_path):
    from piper_train.tools import generate_eval_audio as generation

    base, run = _trained_run(tmp_path)
    manifest = _synthesis_manifest(tmp_path, base)
    with pytest.raises(ValueError, match="torch-ema"):
        generation.generate_audio(
            manifest, "torch-raw", tmp_path / "raw", device="cpu", decoder_run=run
        )


def test_dataset_conditions_on_another_utterance_of_the_same_speaker(tmp_path):
    from piper_train.tools.train_decoder_only import SegmentDataset

    utts = []
    for spk in ("a", "b"):
        for i in range(3):
            np.save(tmp_path / f"{spk}{i}.npy", np.zeros(HOP * 40, np.float32) + i)
            utts.append({"id": f"{spk}{i}", "speaker": spk, "audio": f"{spk}{i}.npy"})
    emb = np.stack([np.full(192, k, np.float32) for k in range(len(utts))])
    np.save(tmp_path / "embeddings.npy", emb)
    (tmp_path / "index.json").write_text(
        json.dumps({"utterances": utts}), encoding="utf-8"
    )
    ds = SegmentDataset(tmp_path, seed=0)
    for i in range(len(ds)):
        item = ds[i]
        row = int(item["speaker_embedding"][0])
        assert row != i and utts[row]["speaker"] == utts[i]["speaker"]
        assert item["audio"].shape == (HOP * 40,)


def test_drifted_pqmf_synthesis_filter_is_never_loaded(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import CANDIDATES, build_models
    from piper_train.vits.mb_istft import PQMF

    path, ckpt = _tiny_checkpoint(tmp_path)
    for key in list(ckpt["state_dict"]):
        if key.endswith("pqmf.synthesis_filter"):
            ckpt["state_dict"][key] = ckpt["state_dict"][key] + 1.0  # drift (F6)
    torch.save(ckpt, path)
    canonical = PQMF(
        subbands=4, taps=ckpt["hyper_parameters"]["pqmf_taps"]
    ).synthesis_filter
    for name in ("d0", "d2-32"):
        models = build_models(load_checkpoint(path), CANDIDATES[name])
        torch.testing.assert_close(models.pqmf.synthesis_filter, canonical)
        torch.testing.assert_close(models.model_g.dec.pqmf.synthesis_filter, canonical)


# ---------------------------------------------------------------------------
# S1 候補 A: 推論経路の z でも decoder を学習する (next-direction impl.md §2-4)
# ---------------------------------------------------------------------------


def _phoneme_batch(n=4, frames=40, n_phonemes=12):
    batch = _batch(n=n, frames=frames)
    g = torch.Generator().manual_seed(7)
    ids = torch.randint(1, 20, (n, n_phonemes), generator=g)
    lengths = torch.tensor([n_phonemes - (i % 3) for i in range(n)])
    for row, length in enumerate(lengths):
        ids[row, int(length) :] = 0
    batch["phoneme_ids"] = ids
    batch["phoneme_lengths"] = lengths
    return batch


def _trainer(tmp_path, *, candidate="d0", ckpt_overrides=None, **config):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import (
        CANDIDATES,
        DecoderTrainer,
        TrainConfig,
        build_models,
    )

    tmp_path.mkdir(parents=True, exist_ok=True)
    path, ckpt = _tiny_checkpoint(tmp_path, **(ckpt_overrides or {}))
    # _trained_run と同じ: fixture の EMA +0.5 では小さな decoder が発散する
    shadow = ckpt["ema_generator_state"]["shadow_params"]
    ckpt["ema_generator_state"]["shadow_params"] = {
        n: v - 0.5 + 0.01 for n, v in shadow.items()
    }
    torch.save(ckpt, path)
    cfg = TrainConfig(**{"segment_frames": 16, "band_disc_ffts": (256, 128), **config})
    models = build_models(load_checkpoint(path), CANDIDATES[candidate])
    return DecoderTrainer(models, cfg, device="cpu")


def _write_p1_data(root, utts):
    root.mkdir(parents=True, exist_ok=True)
    (root / "audio").mkdir(exist_ok=True)
    for u in utts:
        np.save(root / u["audio"], np.zeros(HOP * 40, np.float32))
    np.save(root / "embeddings.npy", np.ones((len(utts), 192), np.float32))
    index = {"spec": {"name": "p1"}, "utterances": utts, "rejected": {}, "hours": 0}
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")


def _p1_utts():
    return [
        {"id": "s1_0001", "speaker": "s1", "audio": "audio/s1_0001.npy"},
        {"id": "s1_0002", "speaker": "s1", "audio": "audio/s1_0002.npy"},
        {"id": "s2_0001", "speaker": "s2", "audio": "audio/s2_0001.npy"},
    ]


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def _jsonl_row(speaker, stem, ids, language_id=0):
    return {
        "text": "あ",
        "audio_path": f"/corpus/moe/wavs/{stem}.wav",
        "speaker": speaker,
        "language_id": language_id,
        "phoneme_ids": ids,
    }


def test_attach_phonemes_joins_by_utterance_id_and_records_the_jsonl(tmp_path):
    from piper_train.embedding_cache import file_sha256
    from piper_train.tools.train_decoder_only import attach_phonemes

    data = tmp_path / "data"
    _write_p1_data(data, _p1_utts())
    jsonl = tmp_path / "dataset.jsonl"
    _write_jsonl(
        jsonl,
        [
            _jsonl_row("other", "x_0001", [1, 4, 2]),
            _jsonl_row("s1", "s1_0001", [1, 5, 0, 6, 2]),
            _jsonl_row("s2", "s2_0001", [1, 7, 2]),
            _jsonl_row("s1", "s1_0002", [1, 8, 0, 9, 0, 3, 2]),
        ],
    )
    before = (data / "index.json").read_text(encoding="utf-8")
    report = attach_phonemes(data, jsonl)
    index = json.loads((data / "index.json").read_text(encoding="utf-8"))
    by_id = {u["id"]: u for u in index["utterances"]}
    assert by_id["s1_0001"]["phoneme_ids"] == [1, 5, 0, 6, 2]
    assert by_id["s1_0002"]["phoneme_ids"] == [1, 8, 0, 9, 0, 3, 2]
    assert by_id["s2_0001"]["phoneme_ids"] == [1, 7, 2]
    assert all(u["language_id"] == 0 for u in index["utterances"])
    assert index["phonemes"]["jsonl_sha256"] == file_sha256(jsonl)
    assert index["phonemes"]["matched"] == 3
    assert report["matched"] == 3
    # 元の index は残す (音声と埋め込みは変えない)
    assert (data / "index.pre-phonemes.json").read_text(encoding="utf-8") == before


def test_attach_phonemes_stops_when_an_utterance_is_missing(tmp_path):
    from piper_train.tools.train_decoder_only import attach_phonemes

    data = tmp_path / "data"
    _write_p1_data(data, _p1_utts())
    jsonl = tmp_path / "dataset.jsonl"
    _write_jsonl(
        jsonl,
        [
            _jsonl_row("s1", "s1_0001", [1, 5, 2]),
            _jsonl_row("s2", "s2_0001", [1, 7, 2]),
        ],
    )
    before = (data / "index.json").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="s1_0002"):
        attach_phonemes(data, jsonl)
    assert (data / "index.json").read_text(encoding="utf-8") == before


def test_attach_phonemes_does_not_take_another_speakers_row(tmp_path):
    from piper_train.tools.train_decoder_only import attach_phonemes

    data = tmp_path / "data"
    _write_p1_data(data, _p1_utts())
    jsonl = tmp_path / "dataset.jsonl"
    _write_jsonl(
        jsonl,
        [
            _jsonl_row("s1", "s1_0001", [1, 5, 2]),
            _jsonl_row("s9", "s1_0002", [1, 6, 2]),  # 同じ stem・別の話者
            _jsonl_row("s2", "s2_0001", [1, 7, 2]),
        ],
    )
    with pytest.raises(ValueError, match="s1_0002"):
        attach_phonemes(data, jsonl)


def test_attach_phonemes_rejects_mixed_language_ids(tmp_path):
    from piper_train.tools.train_decoder_only import attach_phonemes

    data = tmp_path / "data"
    _write_p1_data(data, _p1_utts())
    jsonl = tmp_path / "dataset.jsonl"
    _write_jsonl(
        jsonl,
        [
            _jsonl_row("s1", "s1_0001", [1, 5, -1, 2]),  # 混在言語の印
            _jsonl_row("s1", "s1_0002", [1, 6, 2]),
            _jsonl_row("s2", "s2_0001", [1, 7, 2]),
        ],
    )
    with pytest.raises(ValueError, match="negative"):
        attach_phonemes(data, jsonl)


def test_attach_phonemes_refuses_to_run_twice(tmp_path):
    from piper_train.tools.train_decoder_only import attach_phonemes

    data = tmp_path / "data"
    _write_p1_data(data, _p1_utts())
    jsonl = tmp_path / "dataset.jsonl"
    _write_jsonl(
        jsonl,
        [
            _jsonl_row("s1", "s1_0001", [1, 5, 2]),
            _jsonl_row("s1", "s1_0002", [1, 6, 2]),
            _jsonl_row("s2", "s2_0001", [1, 7, 2]),
        ],
    )
    attach_phonemes(data, jsonl)
    with pytest.raises(ValueError, match="already"):
        attach_phonemes(data, jsonl)


def test_collate_pads_phoneme_ids_and_keeps_language_ids(tmp_path):
    from piper_train.tools.train_decoder_only import SegmentDataset, collate

    data = tmp_path / "data"
    utts = _p1_utts()
    for u, ids in zip(utts, ([1, 5, 2], [1, 6, 0, 7, 2], [1, 8, 2]), strict=True):
        u["phoneme_ids"] = ids
        u["language_id"] = 0
    _write_p1_data(data, utts)
    ds = SegmentDataset(data, seed=0)
    batch = collate([ds[0], ds[1], ds[2]], hop=HOP)
    assert batch["phoneme_ids"].tolist() == [
        [1, 5, 2, 0, 0],
        [1, 6, 0, 7, 2],
        [1, 8, 2, 0, 0],
    ]
    assert batch["phoneme_lengths"].tolist() == [3, 5, 3]
    assert batch["language_ids"].tolist() == [0, 0, 0]


def test_collate_without_phonemes_has_no_phoneme_keys(tmp_path):
    from piper_train.tools.train_decoder_only import SegmentDataset, collate

    data = tmp_path / "data"
    _write_p1_data(data, _p1_utts())
    ds = SegmentDataset(data, seed=0)
    batch = collate([ds[0], ds[1]], hop=HOP)
    assert "phoneme_ids" not in batch


def test_arms_cover_the_s1_table():
    from piper_train.tools.train_decoder_only import ARMS

    assert set(ARMS) == {"extend", "a1", "a1e", "a2"}
    assert ARMS["extend"] == {"z_source": "posterior"}
    assert ARMS["a1"] == {
        "z_source": "prior_noise",
        "prior_noise_scale": 0.4,
        "prior_loss": "full",
    }
    assert ARMS["a1e"] == {
        "z_source": "prior_noise",
        "prior_noise_scale": 0.4,
        "prior_loss": "envelope",
    }
    # 計画書 §7.15: σ_r 0.992 / 0.995 から λ = 0.4/σ_r = 0.40
    assert ARMS["a2"] == {
        "z_source": "prior_residual",
        "residual_scale": 0.40,
        "prior_loss": "full",
    }


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"z_source": "nope"}, "z_source"),
        ({"z_source": "prior_noise", "prior_loss": "nope"}, "prior_loss"),
        ({"z_source": "posterior", "prior_loss": "envelope", "c_env": 1.0}, "envelope"),
        ({"z_source": "prior_noise", "prior_loss": "envelope"}, "c_env"),
        ({"z_source": "prior_residual"}, "residual_scale"),
        ({"z_source": "prior_noise", "prior_fraction": 1.0}, "prior_fraction"),
    ],
)
def test_train_config_rejects_inconsistent_arms(config, message):
    from piper_train.tools.train_decoder_only import TrainConfig

    with pytest.raises(ValueError, match=message):
        TrainConfig(**config)


def test_prior_rows_take_the_inference_path_latent(tmp_path):
    """後半の行は ``prior_path_latent`` の z そのもの (手書きの写しを作らない)。"""
    t = _trainer(
        tmp_path,
        ckpt_overrides={"use_snac_flow": True},
        z_source="prior_noise",
        prior_noise_scale=0.4,
    )
    batch = _phoneme_batch(n=4)
    torch.manual_seed(11)
    lat = t._latents(batch)
    assert lat.n_posterior == 2

    # 同じ乱数の順で、enc_q → prior_path_latent を直接呼ぶ
    m = t.models
    hop = t.hp["hop_length"]
    frames = (batch["audio_lengths"] // hop).long()
    torch.manual_seed(11)
    with torch.no_grad():
        spec = t._spec(batch["audio"].float())[..., : int(frames.max())]
        g = m.model_g._get_global_conditioning(
            None, batch["language_ids"], speaker_embeddings=batch["speaker_embeddings"]
        )
        z_q, _, _, mask = m.model_g.enc_q(spec, frames, g=g)
        expected = m.model_g.prior_path_latent(
            batch["phoneme_ids"][2:],
            batch["phoneme_lengths"][2:],
            z_q[2:],
            mask[2:],
            lid=batch["language_ids"][2:],
            speaker_embeddings=batch["speaker_embeddings"][2:],
            noise_scale=0.4,
        )
    torch.testing.assert_close(lat.z[:2], (z_q * mask)[:2])
    torch.testing.assert_close(lat.z[2:], expected.z)
    assert not torch.allclose(lat.z[2:], (z_q * mask)[2:])


def test_full_residual_gives_back_the_posterior_latent(tmp_path):
    t = _trainer(
        tmp_path,
        ckpt_overrides={"use_snac_flow": True},
        z_source="prior_residual",
        residual_scale=1.0,
    )
    batch = _phoneme_batch(n=4)
    torch.manual_seed(11)
    lat = t._latents(batch)
    post = _trainer(tmp_path / "p", ckpt_overrides={"use_snac_flow": True})
    torch.manual_seed(11)
    expected = post._latents(batch)
    torch.testing.assert_close(lat.z, expected.z, atol=1e-4, rtol=1e-4)


def test_prior_source_needs_phoneme_ids(tmp_path):
    t = _trainer(tmp_path, z_source="prior_noise")
    with pytest.raises(ValueError, match="phoneme_ids"):
        t.step(_batch(n=4))


def test_prior_step_updates_only_the_decoder(tmp_path):
    t = _trainer(
        tmp_path,
        ckpt_overrides={"use_snac_flow": True},
        z_source="prior_noise",
    )
    m = t.models
    frozen = {
        name: {k: v.clone() for k, v in getattr(m.model_g, name).state_dict().items()}
        for name in ("enc_p", "flow", "enc_q", "spk_proj")
    }
    dec = {k: v.clone() for k, v in m.model_g.dec.state_dict().items()}
    logs = t.step(_phoneme_batch(n=4))
    assert all(np.isfinite(v) for v in logs.values())
    for name, state in frozen.items():
        for k, v in getattr(m.model_g, name).state_dict().items():
            torch.testing.assert_close(v, state[k], msg=f"{name}.{k}")
    assert any(
        not torch.equal(v, dec[k]) for k, v in m.model_g.dec.state_dict().items()
    )


def test_full_arm_applies_the_same_losses_to_both_halves(tmp_path):
    t = _trainer(tmp_path, z_source="prior_noise", prior_loss="full")
    logs = t.step(_phoneme_batch(n=4))
    c = t.config
    for part in ("post", "prior"):
        paired = (
            logs[f"loss_gen_{part}"]
            + logs[f"loss_fm_{part}"]
            + logs[f"loss_mel_{part}"]
            + logs[f"loss_full_stft_{part}"]
            + c.c_mrd * (logs[f"loss_gen_mrd_{part}"] + logs[f"loss_fm_mrd_{part}"])
            + c.c_bmrd * (logs[f"loss_gen_bmrd_{part}"] + logs[f"loss_fm_bmrd_{part}"])
            + logs[f"loss_sub_stft_{part}"]
        )
        assert logs[f"loss_total_{part}"] == pytest.approx(paired, rel=1e-5)
    assert logs["loss_all"] == pytest.approx(
        0.5 * logs["loss_total_post"] + 0.5 * logs["loss_total_prior"], rel=1e-5
    )


def test_envelope_arm_drops_paired_losses_on_the_prior_half(tmp_path):
    t = _trainer(tmp_path, z_source="prior_noise", prior_loss="envelope", c_env=3.0)
    logs = t.step(_phoneme_batch(n=4))
    c = t.config
    adversarial = (
        logs["loss_gen_prior"]
        + c.c_mrd * logs["loss_gen_mrd_prior"]
        + c.c_bmrd * logs["loss_gen_bmrd_prior"]
    )
    assert logs["loss_total_prior"] == pytest.approx(
        adversarial + 3.0 * logs["loss_env_prior"], rel=1e-5
    )
    assert logs["loss_all"] == pytest.approx(
        0.5 * logs["loss_total_post"] + 0.5 * logs["loss_total_prior"], rel=1e-5
    )
    # 推論経路の半分の mel は記録だけする (損失には入らない)
    assert logs["loss_mel_prior"] > 0


def test_posterior_only_logs_no_prior_half(tmp_path):
    t = _trainer(tmp_path)
    logs = t.step(_batch(n=4))
    assert logs["loss_all"] == pytest.approx(logs["loss_total_post"], rel=1e-6)
    assert not any(k.endswith("_prior") for k in logs)
    for key in ("d_fake_mpd_post", "d_fake_bmrd_post"):
        assert np.isfinite(logs[key])


def _harmonic(f0, formants, seconds=1.0, sr=22050):
    t = torch.arange(int(seconds * sr)) / sr
    wav = torch.zeros_like(t)
    k = 1
    while k * f0 < sr / 2 - 200:
        f = k * f0
        amp = sum(math.exp(-(((f - c) / 250.0) ** 2)) for c in formants) + 0.02
        wav += amp * torch.sin(2 * math.pi * f * t)
        k += 1
    return (wav / wav.abs().max() * 0.5)[None]


def _log_mel(wav):
    from piper_train.vits.mel_processing import mel_spectrogram_torch

    return mel_spectrogram_torch(wav, 1024, 80, 22050, 256, 1024, 0.0, None)


def test_envelope_loss_is_zero_for_identical_mels():
    from piper_train.tools.train_decoder_only import envelope_l1

    mel = _log_mel(_harmonic(120.0, (700, 1200, 2600)))
    assert float(envelope_l1(mel, mel, n_coeffs=20)) == 0.0


def test_envelope_loss_is_less_sensitive_to_pitch_than_mel_l1():
    """F0 だけ 10% ずらした組は、声の響き (包絡) を変えた組より包絡の損失が小さい。

    mel L1 での同じ比と比べる (impl.md §3.2 の単体テスト)。
    """
    from piper_train.tools.train_decoder_only import envelope_l1

    base = _log_mel(_harmonic(120.0, (700, 1200, 2600)))
    pitch = _log_mel(_harmonic(132.0, (700, 1200, 2600)))
    timbre = _log_mel(_harmonic(120.0, (500, 1700, 3000)))
    env_ratio = float(envelope_l1(base, pitch, n_coeffs=20)) / float(
        envelope_l1(base, timbre, n_coeffs=20)
    )
    mel_ratio = float(F.l1_loss(base, pitch)) / float(F.l1_loss(base, timbre))
    assert env_ratio < 0.5 * mel_ratio


def test_band_split_discriminator_continues_from_the_checkpoint(tmp_path):
    """K1 は帯域分割 MRD を学習済みなので、延長はその重みから続ける。"""
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import (
        CANDIDATES,
        DecoderTrainer,
        TrainConfig,
        build_models,
    )

    path, ckpt = _tiny_checkpoint(tmp_path, use_band_split_mrd=True)
    models = build_models(load_checkpoint(path), CANDIDATES["d0"])
    t = DecoderTrainer(models, TrainConfig(segment_frames=16), device="cpu")
    for k, v in t.bmrd.state_dict().items():
        torch.testing.assert_close(v, ckpt["state_dict"][f"model_d_bmrd.{k}"], msg=k)
    assert t.state("d0")["bmrd_init"] == "checkpoint"
    with pytest.raises(ValueError, match="band_disc_ffts"):
        DecoderTrainer(
            build_models(load_checkpoint(path), CANDIDATES["d0"]),
            TrainConfig(segment_frames=16, band_disc_ffts=(256, 128)),
            device="cpu",
        )


def test_band_split_discriminator_is_fresh_without_one_in_the_checkpoint(tmp_path):
    t = _trainer(tmp_path)
    assert t.state("d0")["bmrd_init"] == "fresh"


def test_scratch_init_does_not_take_the_checkpoint_band_split_discriminator(tmp_path):
    from piper_train.checkpoint_io import load_checkpoint
    from piper_train.tools.train_decoder_only import (
        CANDIDATES,
        DecoderTrainer,
        TrainConfig,
        build_models,
    )

    path, _ = _tiny_checkpoint(tmp_path, use_band_split_mrd=True)
    models = build_models(load_checkpoint(path), CANDIDATES["d1"])
    t = DecoderTrainer(models, TrainConfig(segment_frames=16), device="cpu")
    assert t.state("d1")["bmrd_init"] == "fresh"


def test_resume_refuses_a_different_arm(tmp_path):
    a = _trainer(tmp_path, z_source="prior_noise")
    a.step(_phoneme_batch(n=4))
    run = tmp_path / "run.pt"
    a.save(run, candidate="d0")
    b = _trainer(tmp_path / "b")
    with pytest.raises(ValueError, match="z_source"):
        b.load(run)


def test_envelope_calibration_matches_mel_scale_on_the_prior_half(tmp_path):
    """c_env は、学習前の推論経路の半分で c_env·包絡 = c_mel·mel になる値。"""
    from piper_train.tools.train_decoder_only import calibrate_envelope

    t = _trainer(tmp_path, z_source="prior_noise")
    report = calibrate_envelope(t, [_phoneme_batch(n=4), _phoneme_batch(n=4)])
    assert report["batches"] == 2
    assert report["mel_l1_prior"] > 0 and report["env_l1_prior"] > 0
    assert report["c_env"] == pytest.approx(
        t.config.c_mel * report["mel_l1_prior"] / report["env_l1_prior"]
    )
    assert t.global_step == 0  # 学習はしない


def test_cli_builds_the_config_from_the_arm():
    from piper_train.tools.train_decoder_only import main_parser, train_config

    parser = main_parser()
    base = ["train", "--base-checkpoint", "b.ckpt", "--data", "d", "--out", "o"]
    common = ["--candidate", "d0", "--steps", "10", "--seed", "3"]
    args = parser.parse_args([*base, *common, "--arm", "a2"])
    cfg = train_config(args)
    assert (cfg.z_source, cfg.residual_scale, cfg.seed) == ("prior_residual", 0.40, 3)
    args = parser.parse_args([*base, *common])
    assert train_config(args).z_source == "posterior"  # 既定は延長だけ (P1 と同じ)
    args = parser.parse_args([*base, *common, "--arm", "a1e"])
    with pytest.raises(ValueError, match="c_env"):
        train_config(args)
    args = parser.parse_args([*base, *common, "--arm", "a1e", "--c-env", "2.5"])
    assert train_config(args).c_env == 2.5
    args = parser.parse_args([*base, *common, "--arm", "a1", "--c-env", "2.5"])
    with pytest.raises(ValueError, match="c-env"):
        train_config(args)  # 使わない係数を渡したら止める
