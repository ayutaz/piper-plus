"""Prepare a pinned evaluation manifest or generate unnormalized float WAVs."""

import argparse
import copy
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

import numpy as np

from piper_plus.embedding import embedding_dimension

from ..checkpoint_io import load_checkpoint
from ..embedding_cache import atomic_write, file_sha256
from ..evaluation_manifest import (
    BACKENDS,
    REFERENCE_SPEC_DEFAULTS,
    clip_embedding,
    compute_reference_spec,
    create_manifest,
    load_manifest,
)


def load_torch_generator(path, *, device="auto"):
    """Reuse checkpoint migration; strictly load G without external teachers."""
    import torch  # noqa: PLC0415

    from ..inference_eval import isolated_inference  # noqa: PLC0415
    from ..vits.lightning import VitsModel  # noqa: PLC0415

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    target_device = torch.device(device)
    if target_device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but no CUDA GPU is available")
    checkpoint = load_checkpoint(path)
    parameters = {
        **checkpoint["hyper_parameters"],
        "dataset": None,
        "use_wavlm_discriminator": False,
        "speaker_encoder_path": None,
        "speaker_encoder_torch_path": None,
        "strict_zero_shot": False,
        "c_swap_spk": 0.0,
    }
    with isolated_inference(torch.nn.Module()):
        model = VitsModel(**parameters)
        model.on_load_checkpoint(checkpoint)
        generator_state = {
            name.removeprefix("model_g."): value
            for name, value in checkpoint["state_dict"].items()
            if name.startswith("model_g.")
        }
        model.model_g.load_state_dict(generator_state, strict=True)
        model.model_g.to(target_device)
    return model.model_g, checkpoint, model.hparams.sample_rate


def load_onnx_session(path, seed):
    import onnxruntime  # noqa: PLC0415

    from ..ort_utils import create_session_options  # noqa: PLC0415

    # Offline CLI only: ORT has a process-global seed, with no RNG-state API.
    # Fresh kernels per clip prevent an earlier clip from advancing its stream.
    # Load the pinned original rather than an independently cached graph.
    onnxruntime.set_seed(seed)
    return onnxruntime.InferenceSession(
        str(path),
        sess_options=create_session_options(intra_op_threads=1),
        providers=["CPUExecutionProvider"],
    )


def _prosody(clip):
    features = clip.get("prosody_features")
    if features is None:
        return None
    if len(features) != len(clip["phoneme_ids"]):
        raise ValueError(f"prosody length mismatch: {clip['id']}")
    return np.asarray(
        [
            [item["a1"], item["a2"], item["a3"]] if item else [0, 0, 0]
            for item in features
        ],
        dtype=np.int64,
    )[None, :, :]


def _require_reference_spec_conditions(manifest: dict) -> dict:
    """ref_spec モデルの評価に必要な参照音声と spec 来歴が manifest にあるか検査する。"""
    for clip in manifest["clips"]:
        if not clip["reference_audio"]:
            raise ValueError(
                "reference_conditioning='ref_spec' model requires reference audio "
                f"for every clip (missing for {clip['id']})"
            )
    settings = manifest.get("reference_spec")
    if settings is None:
        raise ValueError(
            "reference_conditioning='ref_spec' model requires a manifest prepared "
            "with --reference-spec (frontend, reference spec hash and T_ref pinned)"
        )
    return settings


def _check_reference_stft(settings: dict, spec_channels, hparams: dict) -> None:
    """モデルの参照 spec 契約 (bin 数・学習 STFT 設定) と manifest の設定を照合する。"""
    expected = settings["filter_length"] // 2 + 1
    if isinstance(spec_channels, int) and spec_channels != expected:
        raise ValueError(
            f"Model expects {spec_channels}-bin reference_spec but manifest "
            f"filter_length={settings['filter_length']} gives {expected} bins"
        )
    for key in ("filter_length", "hop_length", "win_length"):
        if key in hparams and hparams[key] != settings[key]:
            raise ValueError(
                f"Checkpoint {key}={hparams[key]} does not match manifest "
                f"reference_spec {key}={settings[key]}"
            )


def _reference_spec_for_clip(manifest: dict, clip: dict):
    """学習 cache と同じ frontend で参照 spec を作り、manifest の来歴と照合する。

    Returns:
        (spec ``[filter_length // 2 + 1, T_ref]`` float32, 来歴の記録)。
    """
    record = clip.get("reference_spec")
    if record is None:
        raise ValueError(f"Missing reference_spec record for {clip['id']}")
    spec, actual = compute_reference_spec(
        clip["reference_audio"][0]["path"],
        manifest["reference_spec"],
        manifest["sample_rate"],
    )
    if actual["audio_sha256"] != record["audio_sha256"]:
        raise ValueError(f"reference audio hash mismatch for {clip['id']}")
    if actual["frames"] != record["frames"]:
        raise ValueError(
            f"reference spec T_ref mismatch for {clip['id']}: "
            f"{actual['frames']} frames vs pinned {record['frames']}"
        )
    if actual["spec_sha256"] != record["spec_sha256"]:
        raise ValueError(
            f"reference spec hash mismatch for {clip['id']}: the frontend output "
            "differs from the pinned manifest (re-run prepare --reference-spec)"
        )
    return spec, actual


def generate_audio(
    manifest_path: Path, backend: str, output_dir: Path, *, device="auto"
) -> dict:
    """Generate all expected clips; publish a report only on complete success."""
    from ..vits.wavfile import write  # noqa: PLC0415

    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    if backend not in manifest["models"]:
        raise ValueError(f"Backend not pinned in manifest: {backend}")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Evaluation output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    model_spec = manifest["models"][backend]
    generator = None
    restored_weights = None
    ema_report = {}
    # 参照 spec (F-mel) を feed するモデルか。torch は読み込み時、ONNX は
    # 入力名 (reference_spec) で判定する。旧モデル (none / capacity) は False
    uses_reference_spec = False
    if backend in ("torch-raw", "torch-ema"):
        generator, checkpoint, sample_rate = load_torch_generator(
            model_spec["path"], device=device
        )
        if not hasattr(generator, "spk_proj"):
            raise ValueError(
                "Checkpoint does not support speaker_embedding conditioning"
            )
        if getattr(generator, "reference_conditioning", "none") == "ref_spec":
            uses_reference_spec = True
            _check_reference_stft(
                _require_reference_spec_conditions(manifest),
                generator.reference_encoder.spec_channels,
                checkpoint.get("hyper_parameters") or {},
            )
        if (
            manifest.get("training_epoch") is not None
            and checkpoint.get("epoch") != manifest["training_epoch"]
        ):
            raise ValueError("Checkpoint epoch does not match pinned training_epoch")
        if sample_rate != manifest["sample_rate"]:
            raise ValueError("Checkpoint sample_rate does not match manifest")
        if backend == "torch-ema":
            from ..export_onnx import apply_ema_scope_from_checkpoint  # noqa: PLC0415

            restored_weights = copy.deepcopy(generator.state_dict())
            try:
                ema_report = apply_ema_scope_from_checkpoint(generator, checkpoint)
                if not ema_report or any(
                    applied == 0 or skipped != 0
                    for applied, skipped in ema_report.values()
                ):
                    raise ValueError(
                        "EMA shadows missing or incompatible; raw weights cannot be labeled EMA"
                    )
            except Exception:
                generator.load_state_dict(restored_weights)
                raise
    elif backend != "onnx":
        raise ValueError(f"Unsupported backend: {backend}")
    result = {
        "version": 1,
        "backend": backend,
        "execution_device": str(next(generator.parameters()).device)
        if generator is not None
        else "CPUExecutionProvider",
        "manifest_sha256": file_sha256(manifest_path),
        "conditions_sha256": manifest["conditions_sha256"],
        "model_sha256": model_spec["sha256"],
        "source": manifest["source"],
        "sample_rate": manifest["sample_rate"],
        "scales": manifest["scales"],
        "seed": manifest["seed"],
        "training_epoch": checkpoint.get("epoch")
        if generator is not None
        else manifest.get("training_epoch"),
        "ema_applied": ema_report,
        "ground_truth_f0_or_duration": False,
        "audio_encoding": "float32-raw",
        "clips": [],
    }
    if uses_reference_spec:
        result["reference_spec"] = manifest["reference_spec"]
    try:
        for ordinal, clip in enumerate(manifest["clips"]):
            seed = manifest["seed"] + ordinal
            embedding = clip_embedding(clip, manifest["embedding_dimension"])[None, :]
            text = np.asarray(clip["phoneme_ids"], dtype=np.int64)[None, :]
            lengths = np.asarray([text.shape[1]], dtype=np.int64)
            prosody = _prosody(clip)
            reference_spec = reference_record = None
            if uses_reference_spec and generator is not None:
                # ONNX は session の入力名を見てから下で作る
                reference_spec, reference_record = _reference_spec_for_clip(
                    manifest, clip
                )
            if generator is not None:
                import torch  # noqa: PLC0415

                from ..inference_eval import isolated_inference  # noqa: PLC0415

                context = isolated_inference(generator, seed)
            else:
                context = nullcontext()
            with context:
                if generator is not None:
                    device = next(generator.parameters()).device
                    kwargs = {
                        "speaker_embeddings": torch.from_numpy(embedding).to(device),
                        "lid": torch.tensor([clip["language_id"]], device=device),
                        "sid": torch.tensor([clip["speaker_id"]], device=device),
                        "noise_scale": manifest["scales"][0],
                        "length_scale": manifest["scales"][1],
                        "noise_scale_w": manifest["scales"][2],
                    }
                    if prosody is not None:
                        kwargs["prosody_features"] = torch.from_numpy(prosody).to(
                            device
                        )
                    if reference_spec is not None:
                        kwargs["reference_spec"] = reference_spec[None].to(device)
                        kwargs["reference_spec_lengths"] = torch.tensor(
                            [reference_spec.shape[-1]], dtype=torch.long, device=device
                        )
                    audio = (
                        generator.infer(
                            torch.from_numpy(text).to(device),
                            torch.from_numpy(lengths).to(device),
                            **kwargs,
                        )[0]
                        .detach()
                        .cpu()
                        .numpy()
                    )
                else:
                    session = load_onnx_session(model_spec["path"], seed)
                    inputs = session.get_inputs()
                    names = {item.name for item in inputs}
                    if (
                        "speaker_embedding" not in names
                        or embedding_dimension(inputs)
                        != manifest["embedding_dimension"]
                    ):
                        raise ValueError(
                            "ONNX speaker_embedding contract does not match manifest"
                        )
                    if "output" not in {item.name for item in session.get_outputs()}:
                        raise ValueError(
                            "ONNX requires the exported audio output named output"
                        )
                    feeds = {
                        "input": text,
                        "input_lengths": lengths,
                        "scales": np.asarray(manifest["scales"], dtype=np.float32),
                        "speaker_embedding": embedding,
                    }
                    if "sid" in names:
                        feeds["sid"] = np.asarray([clip["speaker_id"]], dtype=np.int64)
                    if "lid" in names:
                        feeds["lid"] = np.asarray([clip["language_id"]], dtype=np.int64)
                    elif clip["language_id"] != 0:
                        raise ValueError("Non-default language requires ONNX lid input")
                    if "speaker_embedding_mask" in names:
                        feeds["speaker_embedding_mask"] = np.ones(
                            (1, 1), dtype=np.int64
                        )
                    if "prosody_features" in names:
                        feeds["prosody_features"] = (
                            prosody
                            if prosody is not None
                            else np.zeros((1, text.shape[1], 3), dtype=np.int64)
                        )
                    elif prosody is not None:
                        raise ValueError(
                            "Reference prosody requires ONNX prosody_features input"
                        )
                    if "reference_spec" in names:
                        if "reference_spec_lengths" not in names:
                            raise ValueError(
                                "ONNX reference_spec input requires the "
                                "reference_spec_lengths input"
                            )
                        spec_input = next(
                            item for item in inputs if item.name == "reference_spec"
                        )
                        _check_reference_stft(
                            _require_reference_spec_conditions(manifest),
                            list(spec_input.shape)[1]
                            if len(spec_input.shape) == 3
                            else None,
                            {},
                        )
                        uses_reference_spec = True
                        result["reference_spec"] = manifest["reference_spec"]
                        reference_spec, reference_record = _reference_spec_for_clip(
                            manifest, clip
                        )
                        feeds["reference_spec"] = np.ascontiguousarray(
                            reference_spec.numpy()[None], dtype=np.float32
                        )
                        feeds["reference_spec_lengths"] = np.asarray(
                            [reference_spec.shape[-1]], dtype=np.int64
                        )
                    audio = session.run(["output"], feeds)[0]
            audio = np.asarray(audio, dtype=np.float32)
            if (
                audio.ndim > 3
                or audio.shape[:-1] not in ((), (1,), (1, 1))
                or audio.size == 0
                or not np.isfinite(audio).all()
            ):
                raise ValueError(f"Invalid generated waveform: {clip['id']}")
            path = output_dir / (clip["id"] + ".wav")
            atomic_write(
                path,
                lambda target, audio=audio: write(
                    target, manifest["sample_rate"], audio.reshape(-1)
                ),
            )
            entry = {
                "id": clip["id"],
                "text_sha256": clip["text_sha256"],
                "speaker_embedding_sha256": clip["speaker_embedding_sha256"],
                "reference_audio": clip["reference_audio"],
                "seed": seed,
                "wav_sha256": file_sha256(path),
            }
            if reference_record is not None:
                # 実際に feed した spec の来歴 (manifest の記録と照合済み)
                entry["reference_spec"] = reference_record
            result["clips"].append(entry)
        atomic_write(
            output_dir / "generation.json",
            lambda target: target.write(
                json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
            ),
        )
        return result
    finally:
        if restored_weights is not None:
            generator.load_state_dict(restored_weights)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--test-jsonl", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--checkpoint", type=Path)
    prepare.add_argument("--onnx", type=Path)
    prepare.add_argument("--sample-rate", type=int, default=22050)
    prepare.add_argument("--embedding-dimension", type=int, default=192)
    prepare.add_argument("--asr-revision", required=True)
    prepare.add_argument("--asr-device", choices=("cuda", "cpu"), default="cuda")
    prepare.add_argument("--source-revision")
    prepare.add_argument("--seed", type=int, default=42)
    prepare.add_argument(
        "--epoch",
        type=int,
        help="Pinned checkpoint/export epoch; unknown epochs cannot pass the promotion gate",
    )
    prepare.add_argument("--scales", type=float, nargs=3, default=[0.4, 1.0, 0.5])
    prepare.add_argument(
        "--reference-spec",
        action="store_true",
        help=(
            "Pin the reference spectrogram (training-cache frontend, spec hash, "
            "T_ref) of each clip's first reference audio; required to evaluate "
            "reference_conditioning='ref_spec' models"
        ),
    )
    for key, value in REFERENCE_SPEC_DEFAULTS.items():
        prepare.add_argument(
            "--reference-" + key.replace("_", "-"),
            type=int,
            default=value,
            help=f"STFT {key} of the reference spectrogram (with --reference-spec)",
        )
    generate = sub.add_parser("generate")
    generate.add_argument("--manifest", required=True, type=Path)
    generate.add_argument("--backend", required=True, choices=BACKENDS)
    generate.add_argument("--output-dir", required=True, type=Path)
    generate.add_argument(
        "--device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="Torch device; auto prefers CUDA, explicit cuda never falls back",
    )
    args = parser.parse_args()
    if args.command == "prepare":
        revision = args.source_revision
        if revision is None:
            root = Path(__file__).resolve().parents[4]
            revision = subprocess.run(
                ["git", "-c", f"safe.directory={root.as_posix()}", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        models = {}
        if args.checkpoint:
            models.update({"torch-raw": args.checkpoint, "torch-ema": args.checkpoint})
        if args.onnx:
            models["onnx"] = args.onnx
        extra = {}
        if args.reference_spec:
            extra["reference_spec"] = {
                key: getattr(args, "reference_" + key)
                for key in REFERENCE_SPEC_DEFAULTS
            }
        create_manifest(
            source_path=args.test_jsonl,
            output_path=args.output,
            models=models,
            sample_rate=args.sample_rate,
            dimension=args.embedding_dimension,
            source_revision=revision,
            asr_revision=args.asr_revision,
            asr_device=args.asr_device,
            seed=args.seed,
            scales=args.scales,
            training_epoch=args.epoch,
            **extra,
        )
    else:
        generate_audio(args.manifest, args.backend, args.output_dir, device=args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
