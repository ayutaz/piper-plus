"""Prepare a pinned evaluation manifest or generate unnormalized float WAVs."""

import argparse
import copy
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

import numpy as np

from piper_plus.embedding import embedding_dimension

from ..embedding_cache import atomic_write, file_sha256
from ..evaluation_manifest import (
    BACKENDS,
    clip_embedding,
    create_manifest,
    load_manifest,
)


def load_torch_generator(path):
    """Reuse checkpoint migration; strictly load G without external teachers."""
    import torch  # noqa: PLC0415

    from ..inference_eval import isolated_inference  # noqa: PLC0415
    from ..vits.lightning import VitsModel  # noqa: PLC0415

    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    parameters = {
        **checkpoint["hyper_parameters"],
        "dataset": None,
        "use_wavlm_discriminator": False,
        "speaker_encoder_path": None,
        "speaker_encoder_torch_path": None,
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


def generate_audio(manifest_path: Path, backend: str, output_dir: Path) -> dict:
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
    if backend in ("torch-raw", "torch-ema"):
        generator, checkpoint, sample_rate = load_torch_generator(model_spec["path"])
        if not hasattr(generator, "spk_proj"):
            raise ValueError(
                "Checkpoint does not support speaker_embedding conditioning"
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
    try:
        for ordinal, clip in enumerate(manifest["clips"]):
            seed = manifest["seed"] + ordinal
            embedding = clip_embedding(clip, manifest["embedding_dimension"])[None, :]
            text = np.asarray(clip["phoneme_ids"], dtype=np.int64)[None, :]
            lengths = np.asarray([text.shape[1]], dtype=np.int64)
            prosody = _prosody(clip)
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
            result["clips"].append(
                {
                    "id": clip["id"],
                    "text_sha256": clip["text_sha256"],
                    "speaker_embedding_sha256": clip["speaker_embedding_sha256"],
                    "reference_audio": clip["reference_audio"],
                    "seed": seed,
                    "wav_sha256": file_sha256(path),
                }
            )
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
    prepare.add_argument("--source-revision")
    prepare.add_argument("--seed", type=int, default=42)
    prepare.add_argument(
        "--epoch",
        type=int,
        help="Pinned checkpoint/export epoch; unknown epochs cannot pass the promotion gate",
    )
    prepare.add_argument("--scales", type=float, nargs=3, default=[0.4, 1.0, 0.5])
    generate = sub.add_parser("generate")
    generate.add_argument("--manifest", required=True, type=Path)
    generate.add_argument("--backend", required=True, choices=BACKENDS)
    generate.add_argument("--output-dir", required=True, type=Path)
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
        create_manifest(
            source_path=args.test_jsonl,
            output_path=args.output,
            models=models,
            sample_rate=args.sample_rate,
            dimension=args.embedding_dimension,
            source_revision=revision,
            asr_revision=args.asr_revision,
            seed=args.seed,
            scales=args.scales,
            training_epoch=args.epoch,
        )
    else:
        generate_audio(args.manifest, args.backend, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
