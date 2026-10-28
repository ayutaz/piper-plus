"""実音声の事後 z を decoder に通す再構成で、decoder が出せる話者再現の上限を測る。

計画書 docs/design/zero-shot-speaker-identity-plan-2026-10-29.md P0-7。
v11 設計 §10.1 の recon bound (つくよみ 1 声) を、評価セットの全群で測り直す
ための音声を作る。各群の実発話 (評価セットの cross 用とは別の発話) を学習と同じ
前処理 (``cache_norm_audio_fast``: energy VAD trim + soxr HQ、音量は変えない) で
spec にし、事後エンコーダー ``enc_q`` から decoder へ直接通す (prior・flow・
duration は通らない)。

    own   enc_q も decoder も、その群の参照 embedding から作った g
    swap  enc_q はその群の g、decoder だけ別の群の g

own は「上流 (prior/flow) を完璧にしたときに decoder が出せる上限」、swap は
「decoder の条件付けが声の主をどれだけ動かすか」を見るためのもの。類似度は
本ツールでは測らない。出力の wav を ``eval_zs_secs`` (第 2 encoder 必須) で測る。

出力:

    <out>/own/<group>/<source stem>.wav
    <out>/swap/<group>/<source stem>.wav
    <out>/recon.json   元音声の sha256、swap の対応、条件

使い方:

    python -m piper_train.tools.measure_recon_bound \\
        --checkpoint <ckpt> --backend torch-ema \\
        --set <built set> --sources <dir with <group>/*.wav> \\
        --swap ja_a=ja_b --swap ja_b=ja_a ... --output <out> [--seed 42]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _spec(
    path: Path, cache: Path, *, sample_rate, filter_length, hop_length, win_length
):
    import torch  # noqa: PLC0415

    from ..norm_audio import cache_norm_audio_fast  # noqa: PLC0415

    _, spec_path = cache_norm_audio_fast(
        path,
        cache,
        sample_rate,
        filter_length=filter_length,
        window_length=win_length,
        hop_length=hop_length,
    )
    return torch.load(spec_path, weights_only=True).float()


def reconstruct(
    generator,
    sources: dict[str, list[Path]],
    embeddings: dict[str, np.ndarray],
    swap: dict[str, str],
    output: Path,
    *,
    sample_rate: int,
    filter_length: int,
    hop_length: int,
    win_length: int,
    seed: int,
    device: str,
    language_id: int = 0,
) -> dict:
    import soundfile as sf  # noqa: PLC0415
    import torch  # noqa: PLC0415

    output = Path(output)
    for group, target in swap.items():
        if group not in sources or target not in embeddings or target == group:
            raise ValueError(f"invalid swap {group!r} -> {target!r}")
    if set(swap) != set(sources):
        raise ValueError("every source group needs a swap target")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")

    def condition(group):
        emb = torch.from_numpy(np.asarray(embeddings[group], dtype=np.float32))
        lid = torch.tensor([language_id], device=device)
        return generator._get_global_conditioning(
            None, lid, speaker_embeddings=emb[None].to(device)
        )

    record = {
        "swap": dict(swap),
        "seed": seed,
        "sample_rate": sample_rate,
        "groups": {},
    }
    generator.eval()
    with tempfile.TemporaryDirectory() as cache, torch.no_grad():
        for group, paths in sources.items():
            g_own, g_dec_swap = condition(group), condition(swap[group])
            rows = []
            for index, path in enumerate(paths):
                spec = _spec(
                    path,
                    Path(cache),
                    sample_rate=sample_rate,
                    filter_length=filter_length,
                    hop_length=hop_length,
                    win_length=win_length,
                )[None].to(device)
                lengths = torch.tensor([spec.shape[2]], device=device)
                for mode, g_dec in (("own", g_own), ("swap", g_dec_swap)):
                    # Same posterior sample for own and swap: only the decoder g differs.
                    torch.manual_seed(seed + index)
                    z, _m, _logs, mask = generator.enc_q(spec, lengths, g=g_own)
                    wav, _ = generator.dec(z * mask, g=g_dec)
                    target = output / mode / group / f"{Path(path).stem}.wav"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    sf.write(
                        target,
                        wav[0, 0].float().cpu().numpy(),
                        sample_rate,
                        subtype="FLOAT",
                    )
                rows.append({"source": str(path), "source_sha256": _sha256(path)})
            record["groups"][group] = rows
    output.mkdir(parents=True, exist_ok=True)
    (output / "recon.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--backend", choices=("torch-raw", "torch-ema"), required=True)
    parser.add_argument("--set", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument(
        "--swap", action="append", required=True, metavar="GROUP=TARGET"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args(argv)

    from .generate_eval_audio import load_torch_generator  # noqa: PLC0415

    generator, checkpoint, sample_rate = load_torch_generator(
        args.checkpoint, device=args.device
    )
    if args.backend == "torch-ema":
        from ..export_onnx import apply_ema_scope_from_checkpoint  # noqa: PLC0415

        report = apply_ema_scope_from_checkpoint(generator, checkpoint)
        if not report or any(a == 0 or s != 0 for a, s in report.values()):
            raise SystemExit(f"EMA shadows missing or incompatible: {report}")
    hparams = checkpoint["hyper_parameters"]
    swap = dict(item.split("=", 1) for item in args.swap)
    sources = {group: sorted((args.sources / group).glob("*.wav")) for group in swap}
    embeddings = {
        path.parent.name: np.load(path)
        for path in (args.set / "groups").glob("*/ref0.npy")
    }
    record = reconstruct(
        generator,
        sources,
        embeddings,
        swap,
        args.output,
        sample_rate=sample_rate,
        filter_length=hparams["filter_length"],
        hop_length=hparams["hop_length"],
        win_length=hparams["win_length"],
        seed=args.seed,
        device=args.device,
    )
    record["checkpoint"] = {
        "path": str(args.checkpoint),
        "sha256": _sha256(args.checkpoint),
    }
    record["backend"] = args.backend
    (args.output / "recon.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"wrote {args.output} ({sum(len(v) for v in sources.values())} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
