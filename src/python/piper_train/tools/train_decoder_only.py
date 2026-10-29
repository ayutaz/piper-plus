"""Train only the decoder on top of a frozen v10b posterior encoder (P1 §5).

P1 decoder design (docs/design/zero-shot-decoder-p1-design-2026-10-29.md §5):
the audible roughness (F4) and the speaker loss in the decoder stage (F1) both
show up in **reconstruction** (real audio -> enc_q -> decoder). So the
candidates are compared by freezing v10b's enc_q and spk_proj and training the
decoder (plus discriminators) alone, which fits on one local GPU.

Common to every candidate (§5.1):

- input: z sampled by the frozen v10b enc_q from real audio, as in training;
  the condition g comes from a CAM++ embedding of *another* utterance of the
  same speaker (the evaluation also conditions on a different utterance);
- the PQMF synthesis filter is fixed to its canonical form (H3);
- a band-split MRD (``vits.band_split_discriminator``) is added to the v10b
  losses and discriminators (H2). The WavLM discriminator is left out for all
  candidates (it sees only < 8 kHz and needs a second large model on the GPU).

Sub-commands::

    prepare   materialise the training data fixed by a spec JSON
    train     train one candidate (resumes from <out>/last.pt)
    recon     write reconstructions of the evaluation groups with the EMA decoder
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import functools
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .measure_variant_cost import load_matching_state, resolve_variant


@dataclasses.dataclass(frozen=True)
class Candidate:
    variant: str  # key of measure_variant_cost.VARIANTS ("a+b" composes)
    init: str  # "v10b": decoder and discriminators start from v10b, "scratch": random
    description: str


CANDIDATES: dict[str, Candidate] = {
    "d0": Candidate("d0-fixed-pqmf", "v10b", "D0: v10b の decoder から再学習"),
    "d1": Candidate("d0-fixed-pqmf", "scratch", "D1: D0 と同じ構成を最初から"),
    "d2-32": Candidate("d2-nfft32", "v10b", "D2: 帯域ごとの iSTFT n_fft 32"),
    "d2-64": Candidate("d2-nfft64", "v10b", "D2: 帯域ごとの iSTFT n_fft 64"),
    "d4": Candidate("d4-adain", "v10b", "D4: resblock ごとの AdaIN"),
    "d5": Candidate("d5-fullband-256", "scratch", "D5: 全帯域 iSTFT dim 256"),
}

_DROP_ALWAYS = ("pqmf.synthesis_filter",)  # the drifted v10b filter (F6) never loads
_DROP_SCRATCH = ("model_g.dec.", "model_d.", "model_d_mrd.")


@dataclasses.dataclass
class Models:
    model_g: nn.Module
    model_d: nn.Module
    model_d_mrd: nn.Module
    pqmf: nn.Module
    sub_stft_loss: nn.Module
    full_stft_loss: nn.Module
    hparams: dict


def build_models(checkpoint: dict, candidate: Candidate) -> Models:
    """v10b with the candidate decoder; enc_q / spk_proj frozen, PQMF fixed."""
    from ..export_onnx import apply_ema_scope_from_checkpoint  # noqa: PLC0415
    from ..inference_eval import isolated_inference  # noqa: PLC0415
    from ..vits.lightning import VitsModel  # noqa: PLC0415

    if candidate.init not in ("v10b", "scratch"):
        raise ValueError(f"unknown init {candidate.init!r}")
    spec = resolve_variant(candidate.variant)
    parameters = {
        **checkpoint["hyper_parameters"],
        "dataset": None,
        "use_wavlm_discriminator": False,
        "speaker_encoder_path": None,
        "speaker_encoder_torch_path": None,
        "strict_zero_shot": False,
        "c_swap_spk": 0.0,
        **spec.overrides,
        "trainable_pqmf_synthesis": False,
    }
    scratch = candidate.init == "scratch"
    with isolated_inference(nn.Module()):
        model = VitsModel(**parameters)
        model.on_load_checkpoint(checkpoint)
        drop = _DROP_ALWAYS + (_DROP_SCRATCH if scratch else ())
        state = {
            k: v
            for k, v in checkpoint["state_dict"].items()
            if not k.startswith(drop) and not k.endswith(_DROP_ALWAYS)
        }
        load_matching_state(model, state)
        ema_source = dict(checkpoint)
        if scratch:
            ema_source.pop("ema_generator_state", None)
        apply_ema_scope_from_checkpoint(model.model_g, ema_source)
        model_g = model.model_g
        before = {
            k: v.clone()
            for k, v in model_g.dec.state_dict().items()
            if not k.endswith(_DROP_ALWAYS)
        }
        hp = dict(model.hparams)
        old_dec = model_g.dec
        for transform in spec.transforms:
            transform(model_g, hp)
        if model_g.dec is not old_dec and not scratch:
            load_matching_state(model_g.dec, before)
    if hasattr(model_g.dec, "pqmf"):
        model_g.dec.pqmf = model.pqmf
    model_g.requires_grad_(False)
    model_g.dec.requires_grad_(True)
    model.pqmf.requires_grad_(False)
    return Models(
        model_g=model_g,
        model_d=model.model_d,
        model_d_mrd=model.model_d_mrd,
        pqmf=model.pqmf,
        sub_stft_loss=model.sub_stft_loss,
        full_stft_loss=model.full_stft_loss,
        hparams=hp,
    )


@dataclasses.dataclass
class TrainConfig:
    segment_frames: int = 64  # v10b segment_size 16384 / hop 256
    lr: float = 2e-4
    betas: tuple[float, float] = (0.8, 0.99)
    eps: float = 1e-9
    grad_clip: float = 1.0
    c_mel: float = 45.0
    c_sub_stft: float = 1.0
    c_full_stft: float = 0.5
    c_mrd: float = 1.0
    c_bmrd: float = 1.0
    band_disc_ffts: tuple[int, ...] = (2048, 1024, 512)
    ema_decay: float = 0.999
    bf16: bool = False
    seed: int = 0


class DecoderTrainer:
    def __init__(self, models: Models, config: TrainConfig, *, device: str):
        from ..vits.band_split_discriminator import (  # noqa: PLC0415
            BandSplitSpectrogramDiscriminator,
        )

        self.models = models
        self.config = config
        self.device = torch.device(device)
        self.hp = models.hparams
        torch.manual_seed(config.seed)
        self.bmrd = BandSplitSpectrogramDiscriminator(fft_sizes=config.band_disc_ffts)
        for m in (
            models.model_g,
            models.model_d,
            models.model_d_mrd,
            models.pqmf,
            models.sub_stft_loss,
            models.full_stft_loss,
            self.bmrd,
        ):
            m.to(self.device)
        models.model_g.eval()  # frozen parts: no dropout in enc_q
        models.model_g.dec.train()
        self.ema = copy.deepcopy(models.model_g.dec).requires_grad_(False).eval()
        self.dec_params = [
            p for p in models.model_g.dec.parameters() if p.requires_grad
        ]
        self.disc_params = [
            *models.model_d.parameters(),
            *models.model_d_mrd.parameters(),
            *self.bmrd.parameters(),
        ]
        opt = {"lr": config.lr, "betas": config.betas, "eps": config.eps}
        self.opt_g = torch.optim.AdamW(self.dec_params, **opt)
        self.opt_d = torch.optim.AdamW(self.disc_params, **opt)
        self.slice_rng = torch.Generator().manual_seed(config.seed)
        self.global_step = 0

    def _autocast(self):
        return torch.autocast(
            self.device.type, dtype=torch.bfloat16, enabled=self.config.bf16
        )

    def _spec(self, audio: torch.Tensor) -> torch.Tensor:
        from ..vits.mel_processing import spectrogram_torch  # noqa: PLC0415

        hp = self.hp
        spec = spectrogram_torch(
            audio,
            n_fft=hp["filter_length"],
            sampling_rate=hp["sample_rate"],
            hop_size=hp["hop_length"],
            win_size=hp["win_length"],
            center=False,
        )
        return spec.half().float()  # the training cache stores spec in fp16

    def step(self, batch: dict) -> dict[str, float]:
        from ..vits.commons import slice_segments  # noqa: PLC0415
        from ..vits.losses import (  # noqa: PLC0415
            discriminator_loss,
            feature_loss,
            generator_loss,
            jcu_split,
        )
        from ..vits.mel_processing import (  # noqa: PLC0415
            mel_spectrogram_torch,
            spec_to_mel_torch,
        )

        cfg, hp, m = self.config, self.hp, self.models
        hop = hp["hop_length"]
        audio = batch["audio"].to(self.device).float()
        emb = batch["speaker_embeddings"].to(self.device).float()
        lid = batch["language_ids"].to(self.device)
        frames = (batch["audio_lengths"].to(self.device) // hop).long()
        seg = cfg.segment_frames

        with torch.no_grad():
            spec = self._spec(audio)[..., : int(frames.max())]
            g = m.model_g._get_global_conditioning(None, lid, speaker_embeddings=emb)
            z, _m_q, _logs_q, mask = m.model_g.enc_q(spec, frames, g=g)
            span = (frames - seg + 1).clamp(min=1).cpu()
            ids = (torch.rand(len(span), generator=self.slice_rng) * span).long()
            ids = ids.to(self.device)
            z_slice = slice_segments(z * mask, ids, seg)
            y = slice_segments(audio[:, None], ids * hop, seg * hop).contiguous()
            mel = spec_to_mel_torch(
                spec,
                hp["filter_length"],
                hp["mel_channels"],
                hp["sample_rate"],
                hp["mel_fmin"],
                hp["mel_fmax"],
            )
            y_mel = slice_segments(mel, ids, seg)

        with self._autocast():
            y_hat, o_mb = m.model_g.dec(z_slice, g=g)
        y_hat = y_hat.float()

        # --- discriminators ---
        y_hat_d = y_hat.detach()
        with self._autocast():
            r, gd, _, _ = m.model_d(y, y_hat_d)
            mr, mg, _, _ = m.model_d_mrd(y, y_hat_d, speaker_embeddings=emb)
            br, bg, _, _ = self.bmrd(y, y_hat_d)
        with torch.autocast(self.device.type, enabled=False):
            loss_d, _, _ = discriminator_loss(r, gd)
            n = m.model_d_mrd.n_resolutions
            (ur, cr), (ug, cg) = jcu_split(mr, n), jcu_split(mg, n)
            loss_d_mrd, _, _ = discriminator_loss(ur, ug)
            if cr:
                loss_d_mrd = 0.5 * (loss_d_mrd + discriminator_loss(cr, cg)[0])
            loss_d_bmrd, _, _ = discriminator_loss(br, bg)
            loss_disc_all = loss_d + cfg.c_mrd * loss_d_mrd + cfg.c_bmrd * loss_d_bmrd
        self.opt_d.zero_grad(set_to_none=True)
        loss_disc_all.backward()
        torch.nn.utils.clip_grad_norm_(self.disc_params, cfg.grad_clip)
        self.opt_d.step()

        # --- decoder ---
        with self._autocast():
            _, gg, fr, fg = m.model_d(y, y_hat)
            _, mgg, mfr, mfg = m.model_d_mrd(y, y_hat, speaker_embeddings=emb)
            _, bgg, bfr, bfg = self.bmrd(y, y_hat)
        with torch.autocast(self.device.type, enabled=False):
            y_hat_mel = mel_spectrogram_torch(
                y_hat.squeeze(1),
                hp["filter_length"],
                hp["mel_channels"],
                hp["sample_rate"],
                hop,
                hp["win_length"],
                hp["mel_fmin"],
                hp["mel_fmax"],
            )
            loss_mel = F.l1_loss(y_mel, y_hat_mel) * cfg.c_mel
            loss_gen, _ = generator_loss(gg)
            loss_fm = feature_loss(fr, fg)
            ug, cg = jcu_split(mgg, m.model_d_mrd.n_resolutions)
            loss_gen_mrd, _ = generator_loss(ug)
            if cg:
                loss_gen_mrd = 0.5 * (loss_gen_mrd + generator_loss(cg)[0])
            loss_fm_mrd = feature_loss(mfr, mfg)
            loss_gen_bmrd, _ = generator_loss(bgg)
            loss_fm_bmrd = feature_loss(bfr, bfg)
            loss_full = m.full_stft_loss(y_hat, y) * cfg.c_full_stft
            loss_all = (
                loss_gen
                + loss_fm
                + loss_mel
                + loss_full
                + cfg.c_mrd * (loss_gen_mrd + loss_fm_mrd)
                + cfg.c_bmrd * (loss_gen_bmrd + loss_fm_bmrd)
            )
            loss_sub = torch.zeros((), device=self.device)
            if o_mb is not None:
                loss_sub = (
                    m.sub_stft_loss(o_mb.float(), m.pqmf.analysis(y)) * cfg.c_sub_stft
                )
                loss_all = loss_all + loss_sub
        self.opt_g.zero_grad(set_to_none=True)
        loss_all.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(self.dec_params, cfg.grad_clip)
        self.opt_g.step()
        self._update_ema()
        self.global_step += 1
        logs = {
            "loss_all": loss_all,
            "loss_mel": loss_mel,
            "loss_gen": loss_gen,
            "loss_fm": loss_fm,
            "loss_gen_mrd": loss_gen_mrd,
            "loss_fm_mrd": loss_fm_mrd,
            "loss_gen_bmrd": loss_gen_bmrd,
            "loss_fm_bmrd": loss_fm_bmrd,
            "loss_full_stft": loss_full,
            "loss_sub_stft": loss_sub,
            "loss_disc_all": loss_disc_all,
            "loss_disc_bmrd": loss_d_bmrd,
            "grad_norm_g": grad_norm,
        }
        return {k: float(v.detach()) for k, v in logs.items()}

    @torch.no_grad()
    def _update_ema(self) -> None:
        d = self.config.ema_decay
        live = dict(self.models.model_g.dec.named_parameters())
        for name, p in self.ema.named_parameters():
            p.lerp_(live[name].detach(), 1.0 - d)

    def state(self, candidate: str) -> dict:
        m = self.models
        return {
            "schema": "decoder-only-run/1",
            "candidate": candidate,
            "variant": CANDIDATES[candidate].variant,
            "init": CANDIDATES[candidate].init,
            "config": dataclasses.asdict(self.config),
            "global_step": self.global_step,
            "dec": m.model_g.dec.state_dict(),
            "dec_ema": self.ema.state_dict(),
            "model_d": m.model_d.state_dict(),
            "model_d_mrd": m.model_d_mrd.state_dict(),
            "bmrd": self.bmrd.state_dict(),
            "opt_g": self.opt_g.state_dict(),
            "opt_d": self.opt_d.state_dict(),
            "rng": {
                "torch": torch.get_rng_state(),
                "cuda": torch.cuda.get_rng_state_all()
                if torch.cuda.is_available()
                else [],
                "slice": self.slice_rng.get_state(),
            },
        }

    def save(self, path: Path, *, candidate: str) -> None:
        path = Path(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        torch.save(self.state(candidate), tmp)
        os.replace(tmp, path)

    def load(self, path: Path) -> dict:
        run = torch.load(path, map_location=self.device, weights_only=False)
        m = self.models
        m.model_g.dec.load_state_dict(run["dec"])
        self.ema.load_state_dict(run["dec_ema"])
        m.model_d.load_state_dict(run["model_d"])
        m.model_d_mrd.load_state_dict(run["model_d_mrd"])
        self.bmrd.load_state_dict(run["bmrd"])
        self.opt_g.load_state_dict(run["opt_g"])
        self.opt_d.load_state_dict(run["opt_d"])
        torch.set_rng_state(run["rng"]["torch"].cpu())
        if run["rng"]["cuda"]:
            torch.cuda.set_rng_state_all([s.cpu() for s in run["rng"]["cuda"]])
        self.slice_rng.set_state(run["rng"]["slice"].cpu())
        self.global_step = int(run["global_step"])
        return run


def load_trained_generator(base_checkpoint: Path, run_path: Path, *, device: str):
    """v10b generator whose decoder is the run's EMA decoder (for evaluation)."""
    from ..checkpoint_io import load_checkpoint  # noqa: PLC0415

    run = torch.load(run_path, map_location="cpu", weights_only=False)
    models = build_models(
        load_checkpoint(base_checkpoint), CANDIDATES[run["candidate"]]
    )
    models.model_g.dec.load_state_dict(run["dec_ema"])
    return models.model_g.to(device).eval()


def trained_decoder(base_checkpoint: dict, run_path: Path) -> tuple[nn.Module, dict]:
    """The run's EMA decoder, built as in training (PQMF fixed), and its record.

    The decoder learned to render the frozen v10b posterior z, which is also
    what the v10b flow produces in synthesis, so it can replace the decoder of
    the v10b TTS path without retraining.
    """
    from ..embedding_cache import file_sha256  # noqa: PLC0415

    run = torch.load(run_path, map_location="cpu", weights_only=False)
    models = build_models(base_checkpoint, CANDIDATES[run["candidate"]])
    models.model_g.dec.load_state_dict(run["dec_ema"])
    record = {
        "path": str(run_path),
        "sha256": file_sha256(run_path),
        "candidate": run["candidate"],
        "global_step": int(run["global_step"]),
    }
    return models.model_g.dec, record


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


class SegmentDataset(torch.utils.data.Dataset):
    """Prepared utterances; each is conditioned on another utterance's embedding."""

    def __init__(self, root: Path, *, seed: int = 0):
        self.root = Path(root)
        index = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        self.utts = index["utterances"]
        self.embeddings = np.load(self.root / "embeddings.npy")
        self.rng = random.Random(seed)
        by_speaker: dict[str, list[int]] = {}
        for i, u in enumerate(self.utts):
            by_speaker.setdefault(u["speaker"], []).append(i)
        self.others = {
            i: [j for j in by_speaker[u["speaker"]] if j != i] or [i]
            for i, u in enumerate(self.utts)
        }

    def __len__(self) -> int:
        return len(self.utts)

    def __getitem__(self, i: int) -> dict:
        audio = np.load(self.root / self.utts[i]["audio"])
        j = self.rng.choice(self.others[i])
        return {
            "audio": torch.from_numpy(np.asarray(audio, dtype=np.float32)),
            "speaker_embedding": torch.from_numpy(
                self.embeddings[j].astype(np.float32)
            ),
        }


def collate(items: list[dict], hop: int) -> dict:
    lengths = [int(it["audio"].numel()) // hop * hop for it in items]
    audio = torch.zeros(len(items), max(lengths))
    for row, (it, n) in enumerate(zip(items, lengths, strict=True)):
        audio[row, :n] = it["audio"][:n]
    return {
        "audio": audio,
        "audio_lengths": torch.tensor(lengths),
        "speaker_embeddings": torch.stack([it["speaker_embedding"] for it in items]),
        "language_ids": torch.zeros(len(items), dtype=torch.long),
    }


def select_speakers(
    available: list[str], exclude: list[str], n: int, seed: int
) -> list[str]:
    pool = sorted(set(available) - set(exclude))
    return sorted(random.Random(seed).sample(pool, n))


def _load_gate(tsv: Path) -> dict[str, tuple[float, float]]:
    gate = {}
    with open(tsv, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        col = {k: i for i, k in enumerate(header)}
        for line in f:
            p = line.rstrip("\n").split("\t")
            gate[Path(p[col["audio_path"]]).name] = (
                float(p[col["hi_ratio"]]),
                float(p[col["fmax999"]]),
            )
    return gate


def prepare(
    spec: dict, zips: Path, band_metrics: Path, campplus: Path, out: Path
) -> dict:
    """Extract, gate, preprocess (as training) and embed the spec's utterances."""
    import tempfile  # noqa: PLC0415
    import zipfile  # noqa: PLC0415

    from ..norm_audio import cache_norm_audio_fast  # noqa: PLC0415
    from .build_zs_eval_set import campplus_embedder  # noqa: PLC0415

    forbidden = set(spec["exclude"]) & set(spec["speakers"])
    if forbidden:
        raise ValueError(f"excluded speakers in the training list: {sorted(forbidden)}")
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory is not empty: {out}")
    (out / "audio").mkdir(parents=True, exist_ok=True)
    gate = _load_gate(band_metrics)
    g_cfg, sr = spec["gate"], spec["sample_rate"]
    lo, hi = spec["duration_s"]
    embed = campplus_embedder(campplus)
    utts, embs, rejected = [], [], {"gate": 0, "no_metrics": 0, "duration": 0}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "cache").mkdir()
        for speaker in spec["speakers"]:
            with zipfile.ZipFile(zips / f"{speaker}.zip") as zf:
                members = sorted(
                    n
                    for n in zf.namelist()
                    if n.startswith(f"data/{speaker}/wav/") and n.endswith(".wav")
                )
                kept = 0
                for name in members:
                    if kept >= spec["per_speaker"]:
                        break
                    base = Path(name).name
                    metrics = gate.get(base)
                    if metrics is None:
                        rejected["no_metrics"] += 1
                        continue
                    if (
                        metrics[0] < g_cfg["hi_ratio_min"]
                        or metrics[1] < g_cfg["fmax999_min"]
                    ):
                        rejected["gate"] += 1
                        continue
                    raw = zf.read(name)
                    src = tmp / base
                    src.write_bytes(raw)
                    norm_path, _ = cache_norm_audio_fast(src, tmp / "cache", sr)
                    audio = np.load(norm_path).reshape(-1).astype(np.float32)
                    if not lo <= audio.size / sr <= hi:
                        rejected["duration"] += 1
                        src.unlink()
                        continue
                    rel = f"audio/{Path(base).stem}.npy"
                    np.save(out / rel, audio)
                    embs.append(np.asarray(embed(src), dtype=np.float32))
                    utts.append(
                        {
                            "id": Path(base).stem,
                            "speaker": speaker,
                            "audio": rel,
                            "member": name,
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "seconds": round(audio.size / sr, 3),
                        }
                    )
                    kept += 1
                    src.unlink()
    np.save(out / "embeddings.npy", np.stack(embs))
    index = {
        "spec": spec,
        "utterances": utts,
        "rejected": rejected,
        "hours": round(sum(u["seconds"] for u in utts) / 3600, 3),
    }
    (out / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return index


# ---------------------------------------------------------------------------
# Reconstruction for evaluation
# ---------------------------------------------------------------------------


def reconstruct_groups(
    generator,
    eval_set: Path,
    sources: Path,
    out: Path,
    *,
    hparams: dict,
    seed: int,
    device: str,
) -> dict:
    """``own`` reconstructions (same layout as measure_recon_bound) of each group."""
    import tempfile  # noqa: PLC0415

    import soundfile as sf  # noqa: PLC0415

    from .measure_recon_bound import _sha256, _spec  # noqa: PLC0415

    record = {}
    with tempfile.TemporaryDirectory() as cache, torch.no_grad():
        for ref in sorted((eval_set / "groups").glob("*/ref0.npy")):
            group = ref.parent.name
            paths = sorted((sources / group).glob("*.wav"))
            if not paths:
                continue
            emb = torch.from_numpy(np.load(ref).astype(np.float32))[None].to(device)
            lid = torch.tensor([0], device=device)
            g = generator._get_global_conditioning(None, lid, speaker_embeddings=emb)
            rows = []
            for index, path in enumerate(paths):
                spec = _spec(
                    path,
                    Path(cache),
                    sample_rate=hparams["sample_rate"],
                    filter_length=hparams["filter_length"],
                    hop_length=hparams["hop_length"],
                    win_length=hparams["win_length"],
                )[None].to(device)
                lengths = torch.tensor([spec.shape[2]], device=device)
                torch.manual_seed(
                    seed + index
                )  # same posterior sample as measure_recon_bound
                z, _m, _logs, mask = generator.enc_q(spec, lengths, g=g)
                wav, _ = generator.dec(z * mask, g=g)
                target = out / group / f"{path.stem}.wav"
                target.parent.mkdir(parents=True, exist_ok=True)
                sf.write(
                    target,
                    wav[0, 0].float().cpu().numpy(),
                    hparams["sample_rate"],
                    subtype="FLOAT",
                )
                rows.append({"source": str(path), "source_sha256": _sha256(path)})
            record[group] = rows
    return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _train(args) -> int:
    from ..checkpoint_io import load_checkpoint  # noqa: PLC0415

    candidate = CANDIDATES[args.candidate]
    args.out.mkdir(parents=True, exist_ok=True)
    config = TrainConfig(bf16=args.bf16, seed=args.seed)
    models = build_models(load_checkpoint(args.base_checkpoint), candidate)
    trainer = DecoderTrainer(models, config, device=args.device)
    last = args.out / "last.pt"
    if last.exists():
        trainer.load(last)
        print(f"resumed at step {trainer.global_step}")
    hop = models.hparams["hop_length"]
    dataset = SegmentDataset(args.data, seed=args.seed + trainer.global_step)
    loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        drop_last=True,
        num_workers=args.num_workers,
        collate_fn=functools.partial(collate, hop=hop),
        persistent_workers=args.num_workers > 0,
        generator=torch.Generator().manual_seed(args.seed + trainer.global_step),
    )
    log = open(args.out / "log.jsonl", "a", encoding="utf-8")  # noqa: SIM115
    meta = args.out / "run.json"
    if not meta.exists():
        meta.write_text(
            json.dumps(
                {
                    "candidate": args.candidate,
                    **dataclasses.asdict(candidate),
                    "config": dataclasses.asdict(config),
                    "base_checkpoint": str(args.base_checkpoint),
                    "data": str(args.data),
                    "batch_size": args.batch_size,
                    "steps": args.steps,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    t0, window = time.time(), []
    try:
        while trainer.global_step < args.steps:
            for batch in loader:
                logs = trainer.step(batch)
                if not all(math.isfinite(v) for v in logs.values()):
                    raise SystemExit(
                        f"non-finite loss at step {trainer.global_step}: {logs}"
                    )
                window.append(logs)
                step = trainer.global_step
                if step % args.log_every == 0:
                    mean = {
                        k: float(np.mean([w[k] for w in window])) for k in window[0]
                    }
                    rate = len(window) / (time.time() - t0)
                    log.write(
                        json.dumps({"step": step, "steps_per_s": rate, **mean}) + "\n"
                    )
                    log.flush()
                    print(
                        f"step {step} {rate:.2f} it/s mel {mean['loss_mel']:.3f} bmrd {mean['loss_gen_bmrd']:.3f} d {mean['loss_disc_all']:.3f}",
                        flush=True,
                    )
                    t0, window = time.time(), []
                if step % args.save_every == 0 or step >= args.steps:
                    trainer.save(last, candidate=args.candidate)
                    if step % args.keep_every == 0 or step >= args.steps:
                        trainer.save(
                            args.out / f"step{step:07d}.pt", candidate=args.candidate
                        )
                if step >= args.steps:
                    break
    finally:
        log.close()
    return 0


def _recon(args) -> int:
    from ..checkpoint_io import load_checkpoint  # noqa: PLC0415

    if (args.run is None) == (args.candidate is None):
        raise SystemExit("give exactly one of --run (trained) or --candidate (step 0)")
    if args.run is not None:
        run = torch.load(args.run, map_location="cpu", weights_only=False)
        generator = load_trained_generator(
            args.base_checkpoint, args.run, device=args.device
        )
        source = {
            "run": str(args.run),
            "candidate": run["candidate"],
            "global_step": run["global_step"],
        }
    else:
        models = build_models(
            load_checkpoint(args.base_checkpoint), CANDIDATES[args.candidate]
        )
        generator = models.model_g.to(args.device).eval()
        source = {"run": None, "candidate": args.candidate, "global_step": 0}
    hparams = load_checkpoint(args.base_checkpoint)["hyper_parameters"]
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit(f"output directory is not empty: {args.out}")
    record = reconstruct_groups(
        generator,
        args.set,
        args.sources,
        args.out,
        hparams=hparams,
        seed=args.seed,
        device=args.device,
    )
    (args.out / "recon.json").write_text(
        json.dumps(
            {**source, "seed": args.seed, "groups": record},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


def _prepare(args) -> int:
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    index = prepare(spec, args.zips, args.band_metrics, args.campplus, args.out)
    print(
        f"{len(index['utterances'])} utterances, {index['hours']} h, rejected {index['rejected']}"
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--zips", type=Path, required=True)
    p.add_argument(
        "--band-metrics", type=Path, required=True, help="v9_band_metrics.tsv"
    )
    p.add_argument("--campplus", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_prepare)

    t = sub.add_parser("train")
    t.add_argument("--base-checkpoint", type=Path, required=True)
    t.add_argument("--data", type=Path, required=True)
    t.add_argument("--candidate", choices=sorted(CANDIDATES), required=True)
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--steps", type=int, required=True)
    t.add_argument("--batch-size", type=int, default=16)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--bf16", action="store_true")
    t.add_argument("--device", default="cuda")
    t.add_argument("--num-workers", type=int, default=2)
    t.add_argument("--log-every", type=int, default=100)
    t.add_argument("--save-every", type=int, default=1000)
    t.add_argument("--keep-every", type=int, default=10000)
    t.set_defaults(func=_train)

    r = sub.add_parser("recon")
    r.add_argument("--base-checkpoint", type=Path, required=True)
    r.add_argument("--run", type=Path, help="trained run (uses its EMA decoder)")
    r.add_argument(
        "--candidate", choices=sorted(CANDIDATES), help="untrained, as built"
    )
    r.add_argument("--set", type=Path, required=True)
    r.add_argument("--sources", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--device", default="cuda")
    r.set_defaults(func=_recon)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
