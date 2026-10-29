"""Measure ONNX size and CPU latency of P1 decoder candidates built from v10b.

The candidates are built from the v10b checkpoint: every parameter whose name
and shape still match is loaded, the rest keep their random init. Size and
speed do not depend on the trained values, so this answers the N5 question
(FP16 40MB, CPU p50 +10%) before any candidate is trained
(docs/design/zero-shot-decoder-p1-design-2026-10-29.md §4).

The prototypes here (fullband iSTFT decoder, reference cross-attention) exist
only for these measurements; they are not wired into training.

Usage::

    uv run python -m piper_train.tools.measure_variant_cost \\
        --checkpoint epoch=79-step=106880.ckpt --manifest manifest.json \\
        --out-dir variant-cost --variants baseline,d2-nfft32,d4-adain-384+flow-2x
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from ..vits.stft_onnx import OnnxISTFT


# ---------------------------------------------------------------------------
# Prototype modules
# ---------------------------------------------------------------------------


class _ConvNeXtBlock(nn.Module):
    """Vocos ConvNeXt block with a per-utterance speaker scale/shift (AdaLN)."""

    def __init__(self, dim: int, intermediate_dim: int, gin_channels: int):
        super().__init__()
        self.dwconv = nn.Conv1d(dim, dim, kernel_size=7, padding=3, groups=dim)
        self.norm = nn.LayerNorm(dim, eps=1e-6, elementwise_affine=False)
        self.pwconv1 = nn.Linear(dim, intermediate_dim)
        self.pwconv2 = nn.Linear(intermediate_dim, dim)
        self.gamma = nn.Parameter(torch.full((dim,), 0.1))
        self.cond = nn.Linear(gin_channels, dim * 2) if gin_channels else None

    def forward(self, x: torch.Tensor, g: torch.Tensor | None) -> torch.Tensor:
        h = self.dwconv(x).transpose(1, 2)  # [B, T, C]
        h = self.norm(h)
        if self.cond is not None and g is not None:
            scale, shift = self.cond(g.transpose(1, 2)).chunk(2, dim=-1)
            h = h * (1 + scale) + shift
        h = self.pwconv2(F.gelu(self.pwconv1(h)))
        return x + (self.gamma * h).transpose(1, 2)


class FullbandISTFTDecoder(nn.Module):
    """D5 prototype: ConvNeXt backbone + one fullband iSTFT (Vocos style).

    Frame rate stays at the latent rate (hop 256), so the time resolution is
    that of the mel frames and the frequency resolution is n_fft/SR (21.5 Hz
    for 1024), against 345 Hz for each band of the 4-band MB-iSTFT.
    """

    def __init__(
        self,
        in_channels: int,
        dim: int = 256,
        intermediate_dim: int = 768,
        num_blocks: int = 8,
        n_fft: int = 1024,
        hop_length: int = 256,
        gin_channels: int = 0,
    ):
        super().__init__()
        self.onnx_export_mode = False
        self.hop_length = hop_length
        self.n_fft = n_fft
        self.embed = nn.Conv1d(in_channels, dim, kernel_size=7, padding=3)
        self.blocks = nn.ModuleList(
            [
                _ConvNeXtBlock(dim, intermediate_dim, gin_channels)
                for _ in range(num_blocks)
            ]
        )
        self.final_norm = nn.LayerNorm(dim, eps=1e-6)
        self.head = nn.Linear(dim, n_fft + 2)
        self.istft = OnnxISTFT(n_fft=n_fft, hop_length=hop_length)

    def forward(self, x, g=None, f0=None, carrier_noise=None):
        frames = x.size(-1)
        h = self.embed(x)
        for block in self.blocks:
            h = block(h, g)
        h = self.head(self.final_norm(h.transpose(1, 2))).transpose(1, 2)
        half = self.n_fft // 2 + 1
        mag = torch.exp(h[:, :half].clamp(max=6.0))
        wav = self.istft(mag, h[:, half:])
        start = (self.n_fft - self.hop_length) // 2
        wav = wav[..., start : start + frames * self.hop_length]
        if self.onnx_export_mode:
            return wav
        return wav, None

    def remove_weight_norm(self) -> None:
        """No weight norm here; export calls this unconditionally."""


class _ReferenceCrossAttention(nn.Module):
    """Residual cross-attention from decoder features to reference tokens.

    The tokens stand in for the per-speaker reference sequence (computed once
    per speaker by a separate encoder); for the cost measurement they are a
    fixed buffer. The output projection starts at zero, so the site is an
    identity until trained.
    """

    def __init__(self, channels: int, n_tokens: int, token_dim: int, n_heads: int = 4):
        super().__init__()
        attn_dim = max(n_heads, (channels // n_heads) * n_heads)
        self.n_heads = n_heads
        self.head_dim = attn_dim // n_heads
        self.register_buffer("tokens", torch.randn(1, n_tokens, token_dim) * 0.1)
        self.norm = nn.LayerNorm(channels)
        self.q = nn.Linear(channels, attn_dim)
        self.k = nn.Linear(token_dim, attn_dim)
        self.v = nn.Linear(token_dim, attn_dim)
        self.out = nn.Linear(attn_dim, channels)
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, _c, t = x.shape
        h = self.norm(x.transpose(1, 2))  # [B, T, C]
        q = self.q(h).reshape(b, t, self.n_heads, self.head_dim).transpose(1, 2)
        tokens = self.tokens.expand(b, -1, -1)
        k = self.k(tokens).reshape(b, -1, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v(tokens).reshape(b, -1, self.n_heads, self.head_dim).transpose(1, 2)
        att = torch.softmax(q @ k.transpose(-1, -2) / math.sqrt(self.head_dim), dim=-1)
        y = (att @ v).transpose(1, 2).reshape(b, t, -1)
        return x + self.out(y).transpose(1, 2)


def add_reference_cross_attention(
    dec: nn.Module, *, n_tokens: int = 32, token_dim: int = 256
) -> list[nn.Module]:
    """Attach one cross-attention site after each upsample stage of ``dec``."""
    sites = []
    for up in dec.ups:
        conv = up.conv if hasattr(up, "conv") else up
        site = _ReferenceCrossAttention(conv.out_channels, n_tokens, token_dim)
        up.register_forward_hook(lambda _m, _inp, out, site=site: site(out))
        sites.append(site)
    dec.ref_cross_attention = nn.ModuleList(sites)
    return sites


class ReferenceTokenEncoder(nn.Module):
    """Reference side of the cross-attention candidate: mel -> K tokens.

    Runs once per speaker, outside the TTS graph; measured for the ~4MB
    reference-encoder budget only.
    """

    def __init__(
        self,
        n_mels: int = 80,
        channels: int = 256,
        n_tokens: int = 32,
        n_layers: int = 4,
    ):
        super().__init__()
        layers = [nn.Conv1d(n_mels, channels, 5, padding=2)]
        for _ in range(n_layers - 1):
            layers += [nn.GELU(), nn.Conv1d(channels, channels, 5, padding=2)]
        self.convs = nn.Sequential(*layers)
        self.queries = nn.Parameter(torch.randn(1, n_tokens, channels) * 0.02)
        self.attn = nn.MultiheadAttention(channels, 4, batch_first=True)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        h = self.convs(mel).transpose(1, 2)
        tokens, _ = self.attn(self.queries.expand(mel.size(0), -1, -1), h, h)
        return tokens


def shrink_flow(
    flow: nn.Module, *, n_flows: int, hidden_channels: int, n_layers: int
) -> nn.Module:
    """A smaller ResidualCouplingBlock with the same interface as ``flow``."""
    from ..vits.models import ResidualCouplingBlock  # noqa: PLC0415

    return ResidualCouplingBlock(
        flow.channels,
        hidden_channels,
        flow.kernel_size,
        flow.dilation_rate,
        n_layers,
        n_flows=n_flows,
        gin_channels=flow.gin_channels,
        use_snac=flow.use_snac,
        snac_stats=flow.snac_stats,
    )


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------


def _rebuild_mb_istft(model_g, hp, **changes) -> None:
    from ..vits.mb_istft import MBiSTFTGenerator  # noqa: PLC0415

    args = {
        "initial_channel": hp["inter_channels"],
        "resblock": hp["resblock"],
        "resblock_kernel_sizes": hp["resblock_kernel_sizes"],
        "resblock_dilation_sizes": hp["resblock_dilation_sizes"],
        "upsample_rates": hp["upsample_rates"],
        "upsample_initial_channel": hp["upsample_initial_channel"],
        "upsample_kernel_sizes": hp["upsample_kernel_sizes"],
        "gin_channels": hp["gin_channels"],
        "film_init_std": hp["film_init_std"],
        "upsample_mode": hp["upsample_mode"],
        "pqmf_taps": hp["pqmf_taps"],
        "trainable_pqmf_synthesis": False,
        "use_adain_decoder": hp.get("use_adain_decoder", False),
        "sample_rate": hp["sample_rate"],
        "f0_frame_hop": hp["hop_length"],
    }
    args.update(changes)
    model_g.dec = MBiSTFTGenerator(**args)


def _fullband(dim: int, blocks: int) -> Callable:
    def apply(model_g, hp) -> None:
        model_g.dec = FullbandISTFTDecoder(
            hp["inter_channels"],
            dim=dim,
            intermediate_dim=dim * 3,
            num_blocks=blocks,
            hop_length=hp["hop_length"],
            gin_channels=hp["gin_channels"],
        )

    return apply


def _flow(n_flows: int, hidden: int, layers: int) -> Callable:
    def apply(model_g, hp) -> None:
        model_g.flow = shrink_flow(
            model_g.flow, n_flows=n_flows, hidden_channels=hidden, n_layers=layers
        )

    return apply


def _xattn(model_g, hp) -> None:
    add_reference_cross_attention(model_g.dec)


@dataclass(frozen=True)
class VariantSpec:
    description: str
    overrides: dict = field(default_factory=dict)
    transforms: tuple[Callable, ...] = ()


_FIXED_PQMF = {"trainable_pqmf_synthesis": False}

VARIANTS: dict[str, VariantSpec] = {
    "baseline": VariantSpec("v10b ep79 そのまま"),
    "d0-fixed-pqmf": VariantSpec(
        "D0/D1: 合成フィルタを固定 (判別器の追加は学習時だけ)", _FIXED_PQMF
    ),
    "d2-nfft32": VariantSpec(
        "D2: 帯域ごとの iSTFT n_fft 16 → 32",
        transforms=(lambda m, hp: _rebuild_mb_istft(m, hp, n_fft=32),),
    ),
    "d2-nfft64": VariantSpec(
        "D2: 帯域ごとの iSTFT n_fft 16 → 64",
        transforms=(lambda m, hp: _rebuild_mb_istft(m, hp, n_fft=64),),
    ),
    "d3-carrier": VariantSpec(
        "D3 の実装済み部分: F0 予測 + v11 carrier head (band0・band1 の 2 帯域)",
        {**_FIXED_PQMF, "use_f0_path": True, "use_carrier_head": True},
    ),
    "d4-adain": VariantSpec(
        "D4: resblock ごとの AdaIN (幅 256 のまま)",
        {**_FIXED_PQMF, "use_adain_decoder": True},
    ),
    "d4-adain-384": VariantSpec(
        "D4: AdaIN + 幅 256 → 384",
        {**_FIXED_PQMF, "use_adain_decoder": True, "upsample_initial_channel": 384},
    ),
    "d4-adain-512": VariantSpec(
        "D4: AdaIN + 幅 256 → 512",
        {**_FIXED_PQMF, "use_adain_decoder": True, "upsample_initial_channel": 512},
    ),
    "d5-fullband-256": VariantSpec(
        "D5: 全帯域 iSTFT (ConvNeXt dim 256 × 8)", transforms=(_fullband(256, 8),)
    ),
    "d5-fullband-384": VariantSpec(
        "D5: 全帯域 iSTFT (ConvNeXt dim 384 × 8)", transforms=(_fullband(384, 8),)
    ),
    "xattn": VariantSpec(
        "参照 32 トークンへの cross-attention を各 upsample 段に追加",
        transforms=(_xattn,),
    ),
    "flow-2x": VariantSpec("flow の段数 4 → 2", transforms=(_flow(2, 192, 4),)),
    "flow-h128": VariantSpec("flow の幅 192 → 128", transforms=(_flow(4, 128, 4),)),
    "flow-2x-h128": VariantSpec(
        "flow の段数 4 → 2、幅 192 → 128", transforms=(_flow(2, 128, 4),)
    ),
}


def resolve_variant(name: str) -> VariantSpec:
    """``a+b`` composes variants: overrides merge, transforms run in order."""
    parts = [VARIANTS[p] for p in name.split("+")]
    overrides: dict = {}
    transforms: list[Callable] = []
    for part in parts:
        overrides.update(part.overrides)
        transforms.extend(part.transforms)
    return VariantSpec(
        " + ".join(p.description for p in parts), overrides, tuple(transforms)
    )


# ---------------------------------------------------------------------------
# Build / export / bench
# ---------------------------------------------------------------------------


def load_matching_state(module: nn.Module, state: dict) -> tuple[list[str], list[str]]:
    """Load every entry whose name and shape match; return (loaded, skipped)."""
    own = module.state_dict()
    loaded, skipped = [], []
    for name, value in state.items():
        if name in own and own[name].shape == value.shape:
            loaded.append(name)
        else:
            skipped.append(name)
    module.load_state_dict({n: state[n] for n in loaded}, strict=False)
    return sorted(loaded), sorted(skipped)


def build_variant(checkpoint: dict, spec: VariantSpec):
    """SynthesizerTrn for ``spec``; matching v10b weights loaded, the rest random."""
    from ..inference_eval import isolated_inference  # noqa: PLC0415
    from ..vits.lightning import VitsModel  # noqa: PLC0415

    parameters = {
        **checkpoint["hyper_parameters"],
        "dataset": None,
        "use_wavlm_discriminator": False,
        "speaker_encoder_path": None,
        "speaker_encoder_torch_path": None,
        "strict_zero_shot": False,
        "c_swap_spk": 0.0,
        **spec.overrides,
    }
    with isolated_inference(torch.nn.Module()):
        model = VitsModel(**parameters)
        model.on_load_checkpoint(checkpoint)
        state = {
            name.removeprefix("model_g."): value
            for name, value in checkpoint["state_dict"].items()
            if name.startswith("model_g.")
        }
        model_g = model.model_g
        _loaded, skipped = load_matching_state(model_g, state)
        hp = dict(model.hparams)
        for transform in spec.transforms:
            transform(model_g, hp)
    return model_g, skipped


def count_parameters(model_g) -> dict[str, int]:
    counts = {
        name: sum(p.numel() for p in child.parameters())
        for name, child in model_g.named_children()
    }
    counts["shipped_total"] = sum(v for k, v in counts.items() if k not in ("enc_q",))
    return counts


def export_variant(model_g, out_fp16: Path) -> None:
    """The export path of ``export_onnx.main`` (EMA and config handling omitted)."""
    from ..export_onnx import (  # noqa: PLC0415
        OPSET_VERSION,
        build_infer_forward,
        set_export_mode,
    )
    from .convert_fp16 import convert_fp16  # noqa: PLC0415

    set_export_mode(model_g, True)
    model_g.eval()
    with torch.no_grad():
        model_g.dec.remove_weight_norm()
    model_g.forward = build_infer_forward(model_g, stochastic=True)

    torch.manual_seed(1234)
    length = 50
    args = [
        torch.randint(0, model_g.n_vocab, (1, length), dtype=torch.long),
        torch.LongTensor([length]),
        torch.FloatTensor([0.4, 1.0, 0.5]),
        torch.zeros(1, 192, dtype=torch.float32),
        torch.LongTensor([0]),
    ]
    names = ["input", "input_lengths", "scales", "speaker_embedding", "lid"]
    axes = {
        "input": {0: "batch_size", 1: "phonemes"},
        "input_lengths": {0: "batch_size"},
        "speaker_embedding": {0: "batch_size"},
        "lid": {0: "batch_size"},
        "output": {0: "batch_size", 2: "time"},
        "durations": {0: "batch_size", 1: "phonemes"},
    }
    if getattr(model_g, "prosody_dim", 0) > 0:
        args.append(torch.zeros(1, length, 3, dtype=torch.long))
        names.append("prosody_features")
        axes["prosody_features"] = {0: "batch_size", 1: "phonemes"}
    with torch.no_grad():
        model_g(*args)
    out_fp16.parent.mkdir(parents=True, exist_ok=True)
    fp32 = out_fp16.with_suffix(".fp32.onnx")
    torch.onnx.export(
        model=model_g,
        args=tuple(args),
        f=str(fp32),
        opset_version=OPSET_VERSION,
        input_names=names,
        output_names=["output", "durations"],
        dynamic_axes=axes,
        dynamo=False,
    )
    convert_fp16(fp32, out_fp16)
    fp32.unlink()


def summarize_latencies(seconds: list[float]) -> dict:
    ms = sorted(s * 1000.0 for s in seconds)
    return {
        "runs": len(ms),
        "p50_ms": statistics.median(ms),
        "p90_ms": ms[min(len(ms) - 1, math.ceil(0.9 * len(ms)) - 1)],
        "mean_ms": statistics.fmean(ms),
        "min_ms": ms[0],
    }


def bench_feeds(manifest: dict, prosody_dim: int) -> dict[str, dict]:
    """Short / median / long ja clips of the evaluation manifest as ORT feeds."""
    from .generate_eval_audio import _prosody, clip_embedding  # noqa: PLC0415

    ja = sorted(
        (c for c in manifest["clips"] if c["language_id"] == 0),
        key=lambda c: len(c["phoneme_ids"]),
    )
    picks = {"short": ja[0], "median": ja[len(ja) // 2], "long": ja[-1]}
    feeds = {}
    for label, clip in picks.items():
        ids = np.asarray([clip["phoneme_ids"]], dtype=np.int64)
        feed = {
            "input": ids,
            "input_lengths": np.asarray([ids.shape[1]], dtype=np.int64),
            # noise_scale_w = 0 keeps durations (and output length) identical
            # across variants, which all share the v10b duration predictor
            "scales": np.asarray([0.667, 1.0, 0.0], dtype=np.float32),
            "speaker_embedding": clip_embedding(clip, manifest["embedding_dimension"])[
                None
            ].astype(np.float32),
            "lid": np.asarray([clip["language_id"]], dtype=np.int64),
        }
        if prosody_dim > 0:
            pr = _prosody(clip)
            feed["prosody_features"] = (
                pr if pr is not None else np.zeros((1, ids.shape[1], 3), np.int64)
            )
        feeds[label] = {"clip": clip["id"], "phonemes": int(ids.shape[1]), "feed": feed}
    return feeds


def bench(
    paths: dict[str, Path], feeds: dict[str, dict], *, warmup: int, runs: int
) -> dict:
    """Round-robin timing so that machine drift hits every variant alike."""
    import onnxruntime  # noqa: PLC0415

    from ..ort_utils import create_session_options  # noqa: PLC0415

    sessions = {}
    for name, path in paths.items():
        opts = create_session_options()
        sessions[name] = onnxruntime.InferenceSession(
            str(path), opts, providers=["CPUExecutionProvider"]
        )
    threads = opts.intra_op_num_threads
    samples = {(n, f): [] for n in sessions for f in feeds}
    lengths = {}
    for name, sess in sessions.items():
        for label, item in feeds.items():
            for _ in range(warmup):
                out = sess.run(["output"], item["feed"])[0]
            lengths[(name, label)] = int(out.shape[-1])
    order = list(sessions)
    for r in range(runs):
        for name in order[r % len(order) :] + order[: r % len(order)]:
            for label, item in feeds.items():
                t0 = time.perf_counter()
                sessions[name].run(["output"], item["feed"])
                samples[(name, label)].append(time.perf_counter() - t0)
    result = {}
    for name in sessions:
        result[name] = {
            label: {
                **summarize_latencies(samples[(name, label)]),
                "samples_out": lengths[(name, label)],
            }
            for label in feeds
        }
    return {"intra_op_threads": threads, "variants": result}


def export_reference_encoder(out_fp16: Path) -> int:
    """Export the reference token encoder prototype; returns its parameter count."""
    from ..export_onnx import OPSET_VERSION  # noqa: PLC0415
    from .convert_fp16 import convert_fp16  # noqa: PLC0415

    enc = ReferenceTokenEncoder().eval()
    fp32 = out_fp16.with_suffix(".fp32.onnx")
    torch.onnx.export(
        enc,
        (torch.randn(1, 80, 430),),
        str(fp32),
        opset_version=OPSET_VERSION,
        input_names=["mel"],
        output_names=["tokens"],
        dynamic_axes={"mel": {0: "batch_size", 2: "frames"}},
        dynamo=False,
    )
    convert_fp16(fp32, out_fp16)
    fp32.unlink()
    return sum(p.numel() for p in enc.parameters())


def main(argv: list[str] | None = None) -> None:
    from ..checkpoint_io import load_checkpoint  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="evaluation manifest (bench inputs)",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--variants", required=True, help="comma-separated; a+b composes variants"
    )
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument(
        "--reference-encoder",
        action="store_true",
        help="also export the reference token encoder",
    )
    parser.add_argument(
        "--extra-onnx",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="also time an existing ONNX (e.g. the official export), repeatable",
    )
    args = parser.parse_args(argv)

    names = [n.strip() for n in args.variants.split(",") if n.strip()]
    specs = {
        n: resolve_variant(n) for n in names
    }  # fail on unknown names before any work
    extra = dict(item.split("=", 1) for item in args.extra_onnx)
    if args.out_dir.exists():
        raise SystemExit(f"refusing to overwrite {args.out_dir}")
    checkpoint = load_checkpoint(args.checkpoint)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    report: dict = {
        "checkpoint": str(args.checkpoint),
        "machine": {"processor": platform.processor(), "platform": platform.platform()},
        "variants": {},
    }
    paths = {}
    prosody_dim = 0
    for name, spec in specs.items():
        model_g, skipped = build_variant(checkpoint, spec)
        prosody_dim = getattr(model_g, "prosody_dim", 0)
        params = count_parameters(model_g)
        path = args.out_dir / f"{name}.onnx"
        export_variant(model_g, path)
        paths[name] = path
        report["variants"][name] = {
            "description": spec.description,
            "parameters": params,
            "random_init_keys": len(skipped),
            "onnx_fp16_bytes": path.stat().st_size,
        }
        print(
            f"{name}: {params['shipped_total'] / 1e6:.2f}M params, {path.stat().st_size / 2**20:.2f} MiB"
        )
        del model_g
    for name, path in extra.items():
        paths[name] = Path(path)
        report["variants"][name] = {
            "description": f"既存の ONNX: {path}",
            "onnx_fp16_bytes": Path(path).stat().st_size,
        }

    feeds = bench_feeds(manifest, prosody_dim)
    report["bench_inputs"] = {
        k: {"clip": v["clip"], "phonemes": v["phonemes"]} for k, v in feeds.items()
    }
    timing = bench(paths, feeds, warmup=args.warmup, runs=args.runs)
    report["intra_op_threads"] = timing["intra_op_threads"]
    for name, per_input in timing["variants"].items():
        report["variants"][name]["latency"] = per_input
    if args.reference_encoder:
        path = args.out_dir / "reference-token-encoder.onnx"
        n = export_reference_encoder(path)
        report["reference_encoder"] = {
            "parameters": n,
            "onnx_fp16_bytes": path.stat().st_size,
        }
    (args.out_dir / "report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    base = report["variants"].get("baseline")
    for name, v in report["variants"].items():
        line = f"{name:28s} {v['onnx_fp16_bytes'] / 2**20:6.2f} MiB"
        for label, lat in v["latency"].items():
            rel = ""
            if base is not None:
                rel = f" ({lat['p50_ms'] / base['latency'][label]['p50_ms'] - 1:+.1%})"
            line += f" | {label} {lat['p50_ms']:7.1f} ms{rel}"
        print(line)


if __name__ == "__main__":
    main()
