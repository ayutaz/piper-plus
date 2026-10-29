"""Decoder-only training for the P1 decoder comparison (design §5)."""

from __future__ import annotations

import json

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")
pytest.importorskip("pytorch_lightning")

from torch.nn import functional as F  # noqa: E402


pytestmark = pytest.mark.unit

HOP = 256
SEG = 16 * HOP


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
        use_mrd=True,
        use_jcu_mrd=True,
        trainable_pqmf_synthesis=True,
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
