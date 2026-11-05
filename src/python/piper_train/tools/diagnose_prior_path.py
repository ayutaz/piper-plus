"""候補 A の事前診断: 同じ発話を 4 通りの z で音にする (next-direction S0)。

docs/design/zero-shot-next-direction-2026-11-05/impl.md §6。C の decoder のまま、
学習に入っていた話者の実録音について、次の 4 通りの音を作る:

    posterior     enc_q の z (今の再構成)
    prior-ns0.4   MAS の並び (実録音にそろえる) + 推論経路の z、noise 0.4
    prior-ns0     同じ並び + noise 0 (prior の平均を flow⁻¹ に通す)
    infer-ns0.4   継続長予測による本来の推論 (評価と同じ scales 0.4/1.0/0.5)

posterior と prior-ns0.4 の差が大きければ、ずれの原因は z の分布の違いで、
候補 A が直接ねらえる。prior-ns0.4 と infer-ns0.4 の差だけが大きければ、原因は
継続長で、A は効きにくい。あわせて σ_r (flow(z_q) − m_p を prior の幅で割った
値の標準偏差、impl.md §2.4) を出す。

条件付けの g は、別の発話の CAM++ 埋め込み (評価と同じ)。出力の layout は
``generate_eval_audio generate`` と同じ (``<out>/<path>/<id>.wav`` +
``generation.json``) なので、``run_zs_eval_set`` / ``measure_highband_deviation``
/ ``eval_cer`` にそのまま渡せる。

Sub-commands::

    pick-speakers  jsonl の話者から、除外を除いて決まった seed で選ぶ
    prepare        評価セット (build_zs_eval_set の layout) と合成する実録音を作る
    generate       1 つの checkpoint (EMA) で 4 通りの音を作る

評価だけの道具で、ここで測る値を学習の損失に使わない (zs-eval-contract §2)。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import tempfile
import zipfile
from pathlib import Path

import numpy as np


PATHS = ("posterior", "prior-ns0.4", "prior-ns0", "infer-ns0.4")
NOISE = {"prior-ns0.4": 0.4, "prior-ns0": 0.0}
SCALES = (0.4, 1.0, 0.5)  # 評価条件 (計画書 §7.3): noise, length, noise_w
SOURCE = "moe-speech-plus"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------


def assign_roles(stems, *, seed: int, n_targets: int, n_cross: int) -> dict:
    """1 名の発話から、参照 1・合成する発話・cross 用の発話を重ならずに選ぶ。"""
    need = 1 + n_targets + n_cross
    ordered = sorted(set(stems))
    if len(ordered) < need:
        raise ValueError(f"{len(ordered)} utterances; needs {need}")
    picked = random.Random(seed).sample(ordered, need)
    return {
        "reference": picked[0],
        "targets": sorted(picked[1 : 1 + n_targets]),
        "cross": sorted(picked[1 + n_targets :]),
    }


def _entry(spk: str, stem: str, role: str, sha256: str) -> dict:
    return {
        "role": role,
        "file": f"{stem}.wav",
        "source": SOURCE,
        "zip": f"{spk}.zip",
        "member": f"data/{spk}/wav/{stem}.wav",
        "sha256": sha256,
    }


def build_spec(speakers: dict, *, floor_per_speaker: int, name: str) -> dict:
    """``build_zs_eval_set`` の仕様 (zs-eval-set-v1) を作る。

    合成する発話の実録音は speaker (cross) に入れない。floor は他の話者の
    cross の先頭 ``floor_per_speaker`` 発話。
    """
    from .build_zs_eval_set import SCHEMA  # noqa: PLC0415

    groups, clips = {}, []
    for spk in sorted(speakers):
        record = speakers[spk]
        roles, sha = record["roles"], record["sha256"]
        files = [
            _entry(spk, stem, "speaker", sha[stem])
            for stem in [roles["reference"], *roles["cross"]]
        ]
        for other in sorted(speakers):
            if other == spk:
                continue
            o = speakers[other]
            for stem in sorted(o["roles"]["cross"])[:floor_per_speaker]:
                files.append(_entry(other, stem, "floor", o["sha256"][stem]))
        group = f"ja_{spk}"
        groups[group] = {"files": files, "references": [f"{roles['reference']}.wav"]}
        for stem in roles["targets"]:
            row = record["rows"][stem]
            clips.append(
                {
                    "id": f"{group}_{stem}",
                    "group": group,
                    "reference": 0,
                    "text": row["text"],
                    "phoneme_ids": row["phoneme_ids"],
                    "language_id": row.get("language_id", 0),
                    "prosody_features": row.get("prosody_features"),
                }
            )
    return {
        "schema": SCHEMA,
        "name": name,
        "sources": {SOURCE: {"kind": "zip-dir"}},
        "groups": groups,
        "clips": clips,
    }


# ---------------------------------------------------------------------------
# latent statistics
# ---------------------------------------------------------------------------


def residual_stats(z_p_posterior, m_p, logs_p, y_mask) -> dict:
    """(flow(z_q) − m_p) / exp(logs_p) の、mask 内の和と二乗和 (σ_r の材料)。"""
    import torch  # noqa: PLC0415

    r = (z_p_posterior - m_p) * torch.exp(-logs_p)
    mask = y_mask.expand_as(r)
    r = r * mask
    return {
        "count": int(mask.sum().item()),
        "sum": float(r.sum().item()),
        "sum_sq": float((r * r).sum().item()),
    }


def pool_residual_stats(items: list[dict]) -> dict:
    count = sum(i["count"] for i in items)
    total = sum(i["sum"] for i in items)
    total_sq = sum(i["sum_sq"] for i in items)
    mean = total / count
    return {
        "count": count,
        "sum": total,
        "sum_sq": total_sq,
        "mean": mean,
        "std": float(np.sqrt(max(total_sq / count - mean * mean, 0.0))),
    }


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------


def _load_generator(checkpoint: Path, device: str):
    """``generate_eval_audio`` の torch-ema と同じ読み込みと EMA の適用。"""
    import copy  # noqa: PLC0415

    from ..export_onnx import apply_ema_scope_from_checkpoint  # noqa: PLC0415
    from .generate_eval_audio import load_torch_generator  # noqa: PLC0415

    generator, ckpt, sample_rate = load_torch_generator(checkpoint, device=device)
    restored = copy.deepcopy(generator.state_dict())
    report = apply_ema_scope_from_checkpoint(generator, ckpt)
    if not report or any(a == 0 or s != 0 for a, s in report.values()):
        generator.load_state_dict(restored)
        raise ValueError("EMA shadows missing or incompatible")
    if getattr(generator, "use_f0_path", False):
        raise NotImplementedError("use_f0_path models need F0 for the posterior path")
    return generator, ckpt, sample_rate, report


def _waveform(out):
    o = out[0] if isinstance(out, tuple) else out
    return o[0, 0].float().cpu().numpy()


def generate(checkpoint: Path, set_dir: Path, out: Path, *, seed: int, device: str):
    """``set_dir`` の合成する発話を 4 通りの z で音にし、``out`` に書く。"""
    import soundfile as sf  # noqa: PLC0415
    import torch  # noqa: PLC0415

    from ..inference_eval import isolated_inference  # noqa: PLC0415
    from .generate_eval_audio import _prosody  # noqa: PLC0415
    from .measure_recon_bound import _spec  # noqa: PLC0415

    checkpoint, set_dir, out = Path(checkpoint), Path(set_dir), Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory is not empty: {out}")
    rows = [
        json.loads(line)
        for line in (set_dir / "test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    targets = {
        t["id"]: t
        for t in json.loads((set_dir / "targets.json").read_text(encoding="utf-8"))[
            "targets"
        ]
    }
    for row in rows:
        target = targets[row["id"]]
        if _sha256(set_dir / target["file"]) != target["sha256"]:
            raise ValueError(f"sha256 of {target['file']} does not match targets.json")

    generator, ckpt, sample_rate, ema_report = _load_generator(checkpoint, device)
    hp = ckpt["hyper_parameters"]
    dev = next(generator.parameters()).device
    clips = {name: [] for name in PATHS}
    stats = {}
    for name in PATHS:
        (out / name).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as cache:
        for ordinal, row in enumerate(rows):
            clip_seed = seed + ordinal
            emb = torch.from_numpy(
                np.load(set_dir / row["speaker_embedding_path"]).astype(np.float32)
            )[None].to(dev)
            lid = torch.tensor([row.get("language_id", 0)], device=dev)
            sid = torch.tensor([row.get("speaker_id", 0)], device=dev)
            x = torch.tensor([row["phoneme_ids"]], dtype=torch.long, device=dev)
            x_lengths = torch.tensor([x.shape[1]], device=dev)
            spec = _spec(
                set_dir / targets[row["id"]]["file"],
                Path(cache),
                sample_rate=hp["sample_rate"],
                filter_length=hp["filter_length"],
                hop_length=hp["hop_length"],
                win_length=hp["win_length"],
            )[None].to(dev)
            spec_lengths = torch.tensor([spec.shape[2]], device=dev)
            for name in PATHS:
                # path ごとに同じ seed: enc_q が最初に乱数を使うので、
                # posterior / prior の 3 通りは同じ z_q から作られる。
                with isolated_inference(generator, clip_seed):
                    g = generator._get_global_conditioning(
                        sid, lid, speaker_embeddings=emb
                    )
                    if name == "infer-ns0.4":
                        kwargs = {}
                        prosody = _prosody(row)
                        if prosody is not None:
                            kwargs["prosody_features"] = torch.from_numpy(prosody).to(
                                dev
                            )
                        wav = _waveform(
                            generator.infer(
                                x,
                                x_lengths,
                                sid=sid,
                                lid=lid,
                                speaker_embeddings=emb,
                                noise_scale=SCALES[0],
                                length_scale=SCALES[1],
                                noise_scale_w=SCALES[2],
                                **kwargs,
                            )
                        )
                    else:
                        z_q, _m, _logs, mask = generator.enc_q(spec, spec_lengths, g=g)
                        if name == "posterior":
                            wav = _waveform(generator.dec(z_q * mask, g=g))
                        else:
                            lat = generator.prior_path_latent(
                                x,
                                x_lengths,
                                z_q,
                                mask,
                                sid=sid,
                                lid=lid,
                                speaker_embeddings=emb,
                                noise_scale=NOISE[name],
                            )
                            wav = _waveform(generator.dec(lat.z, g=g))
                            if name == "prior-ns0.4":
                                stats[row["id"]] = residual_stats(
                                    lat.z_p_posterior, lat.m_p, lat.logs_p, mask
                                )
                path = out / name / f"{row['id']}.wav"
                sf.write(path, wav, sample_rate, subtype="FLOAT")
                clips[name].append({"id": row["id"], "wav_sha256": _sha256(path)})

    model_sha256 = _sha256(checkpoint)
    for name in PATHS:
        record = {
            "version": 1,
            "backend": "torch-ema",
            "z_path": name,
            "noise_scale": SCALES[0] if name == "infer-ns0.4" else NOISE.get(name),
            "scales": list(SCALES) if name == "infer-ns0.4" else None,
            "seed": seed,
            "sample_rate": sample_rate,
            "training_epoch": ckpt.get("epoch"),
            "model_sha256": model_sha256,
            "set": str(set_dir.resolve()),
            "ema_applied": ema_report,
            "audio_encoding": "float32-raw",
            "clips": clips[name],
        }
        (out / name / "generation.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    pooled = pool_residual_stats(list(stats.values()))
    (out / "latent_stats.json").write_text(
        json.dumps(
            {
                "what": "sigma_r: (flow(z_q) - m_p) / exp(logs_p) over masked frames "
                "and channels (impl.md §2.4)",
                "pooled": pooled,
                "clips": stats,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return {"paths": clips, "latent_stats": pooled}


# ---------------------------------------------------------------------------
# data preparation
# ---------------------------------------------------------------------------


def _jsonl_rows(path: Path, contains: str):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if contains not in line:
                continue
            row = json.loads(line)
            if contains in row["audio_path"]:
                yield row


def pick_speakers(
    jsonl: Path, *, exclude: set[str], n: int, seed: int, contains: str
) -> list[str]:
    speakers = {row["speaker"] for row in _jsonl_rows(jsonl, contains)}
    pool = sorted(speakers - exclude)
    if len(pool) < n:
        raise ValueError(f"only {len(pool)} speakers left after exclusion")
    return sorted(random.Random(seed).sample(pool, n))


def prepare(
    jsonl: Path,
    zips: Path,
    speakers: list[str],
    out: Path,
    campplus: Path,
    *,
    seed: int,
    n_targets: int,
    n_cross: int,
    floor_per_speaker: int,
    duration: tuple[float, float],
    contains: str,
) -> dict:
    import soundfile as sf  # noqa: PLC0415

    from .build_zs_eval_set import campplus_embedder, materialize  # noqa: PLC0415

    wanted = set(speakers)
    rows: dict[str, dict[str, dict]] = {s: {} for s in speakers}
    for row in _jsonl_rows(jsonl, contains):
        if row["speaker"] in wanted:
            rows[row["speaker"]][Path(row["audio_path"]).stem] = row
    chosen, payload = {}, {}
    for spk in speakers:
        with zipfile.ZipFile(Path(zips) / f"{spk}.zip") as archive:
            names = set(archive.namelist())
            ok, sha = [], {}
            for stem in sorted(rows[spk]):
                member = f"data/{spk}/wav/{stem}.wav"
                if member not in names:
                    continue
                data = archive.read(member)
                seconds = sf.info(io.BytesIO(data)).duration
                if duration[0] <= seconds <= duration[1]:
                    ok.append(stem)
                    sha[stem] = hashlib.sha256(data).hexdigest()
                    payload[(spk, stem)] = data
        roles = assign_roles(ok, seed=seed, n_targets=n_targets, n_cross=n_cross)
        chosen[spk] = {"roles": roles, "rows": rows[spk], "sha256": sha}
    spec = build_spec(
        chosen, floor_per_speaker=floor_per_speaker, name="diag-prior-path"
    )
    materialize(spec, {SOURCE: Path(zips)}, out, campplus_embedder(campplus))
    targets, texts = [], []
    for spk in speakers:
        for stem in chosen[spk]["roles"]["targets"]:
            clip_id = f"ja_{spk}_{stem}"
            rel = f"targets/ja_{spk}/{clip_id}.wav"
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(payload[(spk, stem)])
            targets.append(
                {
                    "id": clip_id,
                    "file": rel,
                    "sha256": chosen[spk]["sha256"][stem],
                    "member": f"data/{spk}/wav/{stem}.wav",
                }
            )
            texts.append(f"{clip_id}\t{chosen[spk]['rows'][stem]['text']}\n")
    (out / "targets.json").write_text(
        json.dumps({"targets": targets}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "texts.tsv").write_text("".join(texts), encoding="utf-8")
    selection = {
        "speakers": speakers,
        "seed": seed,
        "n_targets": n_targets,
        "n_cross": n_cross,
        "floor_per_speaker": floor_per_speaker,
        "duration_s": list(duration),
        "jsonl": str(jsonl),
        "jsonl_sha256": _sha256(jsonl),
        "roles": {spk: chosen[spk]["roles"] for spk in speakers},
    }
    (out / "selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return selection


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pick-speakers")
    p.add_argument("--jsonl", type=Path, required=True)
    p.add_argument("--exclude-spec", type=Path, action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--contains", default="moe-plus")

    q = sub.add_parser("prepare")
    q.add_argument("--jsonl", type=Path, required=True)
    q.add_argument("--zips", type=Path, required=True)
    q.add_argument("--speakers", nargs="+", required=True)
    q.add_argument("--campplus", type=Path, required=True)
    q.add_argument("--out", type=Path, required=True)
    q.add_argument("--seed", type=int, required=True)
    q.add_argument("--n-targets", type=int, default=10)
    q.add_argument("--n-cross", type=int, default=10)
    q.add_argument("--floor-per-speaker", type=int, default=2)
    q.add_argument("--duration", type=float, nargs=2, default=[2.0, 12.0])
    q.add_argument("--contains", default="moe-plus")

    g = sub.add_parser("generate")
    g.add_argument("--checkpoint", type=Path, required=True)
    g.add_argument("--set", type=Path, required=True)
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--device", default="cpu")

    args = parser.parse_args(argv)
    if args.command == "pick-speakers":
        exclude = set(args.exclude)
        for path in args.exclude_spec:
            spec = json.loads(path.read_text(encoding="utf-8"))
            exclude |= set(spec.get("speakers", ())) | set(spec.get("exclude", ()))
        chosen = pick_speakers(
            args.jsonl,
            exclude=exclude,
            n=args.n,
            seed=args.seed,
            contains=args.contains,
        )
        print(" ".join(chosen))
    elif args.command == "prepare":
        selection = prepare(
            args.jsonl,
            args.zips,
            args.speakers,
            args.out,
            args.campplus,
            seed=args.seed,
            n_targets=args.n_targets,
            n_cross=args.n_cross,
            floor_per_speaker=args.floor_per_speaker,
            duration=tuple(args.duration),
            contains=args.contains,
        )
        print(json.dumps(selection["roles"], ensure_ascii=False))
    else:
        record = generate(
            args.checkpoint, args.set, args.out, seed=args.seed, device=args.device
        )
        print(
            f"sigma_r {record['latent_stats']['std']:.3f} (mean {record['latent_stats']['mean']:+.3f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
