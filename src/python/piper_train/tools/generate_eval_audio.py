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
    load_reference_spec,
)
from ..reference_spec_contract import (
    REFERENCE_MAX_FRAMES_DEFAULT,
    REFERENCE_SPEC_FRONTENDS,
    REFERENCE_SPEC_SCHEMA,
    frontend_steps,
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
            "with --reference-spec --reference-frontend <name> (frontend, stored "
            "reference spec, its hash and T_ref pinned)"
        )
    return settings


# モデルが宣言する参照 spec 契約のうち manifest の reference_spec と照合する項目
_CONTRACT_FIELDS = (
    "frontend",
    "filter_length",
    "hop_length",
    "win_length",
    "center",
    "spec_channels",
)
# export (Task 8R / 11R) が書く config の reference_conditioning (ref_spec_v1)
# の field 全部。max_frames (学習の reference_max_frames) は manifest と照合
# せず、feed 時の先頭切り出しの長さに使う (Ruling R15)
_ONNX_BLOCK_FIELDS = ("schema", *_CONTRACT_FIELDS, "sample_rate", "max_frames")


def _max_frames(value, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"{source}: reference max_frames must be a positive int, got {value!r}"
        )
    return value


def _torch_reference_contract(generator, checkpoint: dict) -> dict:
    """checkpoint hparams (STFT・sample rate・学習 frontend・最大 frame 数) と bin 数。

    学習 frontend (hparams ``reference_spec_frontend``) を宣言していない ref_spec
    checkpoint は manifest の frontend と照合できないので拒否する。最大 frame 数
    は学習と同じ読み方 (``reference_max_frames``、無ければ学習の既定値)。
    """
    hparams = checkpoint.get("hyper_parameters") or {}
    for key in ("filter_length", "hop_length", "win_length", "sample_rate"):
        if key not in hparams:
            raise ValueError(
                f"ref_spec checkpoint hyper_parameters lack {key}; cannot verify "
                "the reference spec contract against the manifest"
            )
    frontend = hparams.get("reference_spec_frontend")
    if frontend is None:
        raise ValueError(
            "ref_spec checkpoint hyper_parameters lack reference_spec_frontend "
            "(the training spec cache builder); the manifest's reference frontend "
            "cannot be verified, so the model is not evaluated"
        )
    frontend_steps(frontend)  # 閉じた集合の外は ValueError
    return {
        "source": "checkpoint hyper_parameters",
        "frontend": frontend,
        "filter_length": hparams["filter_length"],
        "hop_length": hparams["hop_length"],
        "win_length": hparams["win_length"],
        "center": False,  # 学習 cache の spectrogram_torch は center=False 固定
        "spec_channels": generator.reference_encoder.spec_channels,
        "sample_rate": hparams["sample_rate"],
        "max_frames": _max_frames(
            hparams.get("reference_max_frames", REFERENCE_MAX_FRAMES_DEFAULT),
            "checkpoint hyper_parameters",
        ),
    }


def _onnx_config_path(model_path: Path) -> Path:
    """export が書く ``<model>.onnx.json`` (同じ dir の別名 config は読まない)。"""
    model_path = Path(model_path)
    candidate = model_path.with_name(model_path.name + ".json")
    if candidate.is_file():
        return candidate
    raise ValueError(
        f"ONNX ref_spec model requires {candidate.name} (written by "
        "piper_train.export_onnx --config) with a reference_conditioning block; "
        f"not found for {model_path}"
    )


def _onnx_reference_contract(model_path: Path, spec_input) -> dict:
    """``<model>.onnx.json`` の ``reference_conditioning`` (8R/11R 契約) を読み検査する。"""
    config_path = _onnx_config_path(model_path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unreadable ONNX config {config_path}: {exc}") from exc
    block = config.get("reference_conditioning") if isinstance(config, dict) else None
    if not isinstance(block, dict):
        raise ValueError(
            f"ONNX config {config_path} has no reference_conditioning block; the "
            "reference spec contract of this ref_spec model cannot be verified"
        )
    for field in _ONNX_BLOCK_FIELDS:
        if field not in block:
            raise ValueError(f"reference_conditioning in {config_path} lacks {field}")
    unknown = sorted(set(block) - set(_ONNX_BLOCK_FIELDS))
    if unknown:
        raise ValueError(
            f"reference_conditioning in {config_path} has fields outside the "
            f"{REFERENCE_SPEC_SCHEMA} contract: {unknown}"
        )
    if block["schema"] != REFERENCE_SPEC_SCHEMA:
        raise ValueError(
            f"reference_spec schema mismatch: model declares {block['schema']!r}, "
            f"expected {REFERENCE_SPEC_SCHEMA!r}"
        )
    shape = list(spec_input.shape)
    graph_channels = shape[1] if len(shape) == 3 else None
    if isinstance(graph_channels, int) and graph_channels != block["spec_channels"]:
        raise ValueError(
            f"reference_spec spec_channels mismatch: ONNX input has {graph_channels} "
            f"bins but {config_path.name} declares {block['spec_channels']!r}"
        )
    return {
        "source": str(config_path.resolve()),
        "config_sha256": file_sha256(config_path),
        **{field: block[field] for field in _CONTRACT_FIELDS},
        "sample_rate": block["sample_rate"],
        "max_frames": _max_frames(block["max_frames"], str(config_path)),
    }


def _same(model_value, manifest_value) -> bool:
    # True == 1 等の型違いの一致を通さない (center=1 を False と区別する)
    return type(model_value) is type(manifest_value) and model_value == manifest_value


def _check_reference_contract(manifest: dict, contract: dict) -> None:
    """モデルの宣言 (contract) と manifest の reference_spec を項目ごとに照合する。"""
    settings = manifest["reference_spec"]
    pairs = [(field, contract[field], settings[field]) for field in _CONTRACT_FIELDS]
    pairs.append(("sample_rate", contract["sample_rate"], manifest["sample_rate"]))
    for field, declared, pinned in pairs:
        if not _same(declared, pinned):
            raise ValueError(
                f"reference_spec {field} mismatch: model declares {declared!r}, "
                f"manifest has {pinned!r} (re-run prepare with the model's "
                "reference spec settings)"
            )


def _head_crop(spec: np.ndarray, max_frames: int) -> np.ndarray:
    """学習の検証と同じ先頭固定の切り出し (``crop_reference_specs`` mode="head")。"""
    import torch  # noqa: PLC0415

    from ..vits.dataset import crop_reference_specs  # noqa: PLC0415

    cropped, _lengths = crop_reference_specs(
        torch.from_numpy(spec)[None],
        torch.tensor([spec.shape[-1]], dtype=torch.long),
        max_frames,
        mode="head",
    )
    return np.ascontiguousarray(cropped[0].numpy())


def _reference_spec_for_clip(manifest: dict, clip: dict, max_frames: int):
    """prepare で保存した参照 spec を読み、先頭から ``max_frames`` に切って返す。

    再計算は drift の記録だけに使う (別 machine の FFT・soxr の差で結果が
    変わっても評価条件は保存 bytes で固定される)。参照 WAV 自体が変わって
    いたら拒否する。切り出しは feed 時だけで、保存 bytes は全長のまま (学習も
    全長の spec から検証時に先頭を切る、Ruling R15)。

    Returns:
        (feed する spec ``[spec_channels, min(T_ref, max_frames)]`` float32
        ndarray, 来歴の記録 (``frames`` = 保存 spec の T_ref、``fed_frames`` =
        feed した frame 数) + drift)。
    """
    settings = manifest["reference_spec"]
    record = clip["reference_spec"]
    stored = load_reference_spec(clip, settings)
    drift = {
        "recomputed_spec_sha256": None,
        "recomputed_frames": None,
        "bit_exact": False,
        "max_abs_diff": None,
    }
    try:
        recomputed, actual = compute_reference_spec(
            clip["reference_audio"][0]["path"], settings, manifest["sample_rate"]
        )
    except ValueError as exc:
        drift["error"] = str(exc)
    else:
        if actual["audio_sha256"] != record["audio_sha256"]:
            raise ValueError(f"reference audio hash mismatch for {clip['id']}")
        drift["recomputed_spec_sha256"] = actual["spec_sha256"]
        drift["recomputed_frames"] = actual["frames"]
        drift["bit_exact"] = actual["spec_sha256"] == record["spec_sha256"]
        if actual["frames"] == record["frames"]:
            drift["max_abs_diff"] = float(
                np.max(np.abs(recomputed.detach().cpu().numpy() - stored))
            )
    fed = _head_crop(stored, max_frames)
    return fed, {**record, "fed_frames": int(fed.shape[-1]), "drift": drift}


def generate_audio(
    manifest_path: Path,
    backend: str,
    output_dir: Path,
    *,
    device="auto",
    decoder_run: Path | None = None,
) -> dict:
    """Generate all expected clips; publish a report only on complete success.

    ``decoder_run`` (torch-ema only) replaces the EMA decoder with the EMA
    decoder of a ``train_decoder_only`` run; the report records the run.
    """
    from ..vits.wavfile import write  # noqa: PLC0415

    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    if backend not in manifest["models"]:
        raise ValueError(f"Backend not pinned in manifest: {backend}")
    if decoder_run is not None and backend != "torch-ema":
        raise ValueError("--decoder-run replaces the EMA decoder: use torch-ema")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Evaluation output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    model_spec = manifest["models"][backend]
    generator = None
    restored_weights = None
    original_decoder = None
    decoder_record = None
    ema_report = {}
    # 参照 spec (F-mel) を feed するモデルなら、モデルが宣言する参照 spec 契約
    # (torch: checkpoint hparams、ONNX: <model>.onnx.json の reference_conditioning)。
    # 判定は loop の前に 1 回 (torch は読み込み時、ONNX は先頭 clip の session の
    # 入力名)。旧モデル (none / capacity) は None で、評価出力は変更前と同じ
    reference_contract = None
    first_session = None
    if backend in ("torch-raw", "torch-ema"):
        generator, checkpoint, sample_rate = load_torch_generator(
            model_spec["path"], device=device
        )
        if not hasattr(generator, "spk_proj"):
            raise ValueError(
                "Checkpoint does not support speaker_embedding conditioning"
            )
        if getattr(generator, "reference_conditioning", "none") == "ref_spec":
            _require_reference_spec_conditions(manifest)
            reference_contract = _torch_reference_contract(generator, checkpoint)
            _check_reference_contract(manifest, reference_contract)
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
            if decoder_run is not None:
                from .train_decoder_only import trained_decoder  # noqa: PLC0415

                decoder, decoder_record = trained_decoder(checkpoint, decoder_run)
                original_decoder = generator.dec
                generator.dec = decoder.to(next(generator.parameters()).device)
    elif backend == "onnx":
        # 先頭 clip の session (seed も先頭 clip のもの) を loop でそのまま使う
        first_session = load_onnx_session(model_spec["path"], manifest["seed"])
        inputs = {item.name: item for item in first_session.get_inputs()}
        if "reference_spec" in inputs:
            if "reference_spec_lengths" not in inputs:
                raise ValueError(
                    "ONNX reference_spec input requires the reference_spec_lengths input"
                )
            _require_reference_spec_conditions(manifest)
            reference_contract = _onnx_reference_contract(
                model_spec["path"], inputs["reference_spec"]
            )
            _check_reference_contract(manifest, reference_contract)
    else:
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
    if reference_contract is not None:
        result["reference_spec"] = {
            "settings": manifest["reference_spec"],
            "model_contract": reference_contract,
        }
    if decoder_record is not None:
        result["decoder_run"] = decoder_record
    try:
        for ordinal, clip in enumerate(manifest["clips"]):
            seed = manifest["seed"] + ordinal
            embedding = clip_embedding(clip, manifest["embedding_dimension"])[None, :]
            text = np.asarray(clip["phoneme_ids"], dtype=np.int64)[None, :]
            lengths = np.asarray([text.shape[1]], dtype=np.int64)
            prosody = _prosody(clip)
            reference_spec = reference_record = None
            if reference_contract is not None:
                # prepare で保存した bytes (hash 照合・有限性検査済み) を feed する
                reference_spec, reference_record = _reference_spec_for_clip(
                    manifest, clip, reference_contract["max_frames"]
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
                        kwargs["reference_spec"] = torch.from_numpy(
                            reference_spec[None]
                        ).to(device)
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
                    session = (
                        first_session
                        if ordinal == 0
                        else load_onnx_session(model_spec["path"], seed)
                    )
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
                    if reference_spec is not None:
                        feeds["reference_spec"] = np.ascontiguousarray(
                            reference_spec[None], dtype=np.float32
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
                # 実際に feed した保存 spec の来歴と、再計算との drift
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
        if original_decoder is not None:
            generator.dec = original_decoder
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
            "Compute, store (float32 .npy next to the manifest) and pin the "
            "reference spectrogram (frontend, spec hash, T_ref) of each clip's "
            "single reference audio; required to evaluate "
            "reference_conditioning='ref_spec' models. Needs --reference-frontend"
        ),
    )
    prepare.add_argument(
        "--reference-frontend",
        choices=sorted(REFERENCE_SPEC_FRONTENDS),
        help=(
            "Reference spec frontend; must mirror the training cache builder of "
            "the evaluated model (no default; required with --reference-spec)"
        ),
    )
    for key, value in REFERENCE_SPEC_DEFAULTS.items():
        prepare.add_argument(
            "--reference-" + key.replace("_", "-"),
            type=int,
            help=(
                f"STFT {key} of the reference spectrogram (with --reference-spec; "
                f"default {value})"
            ),
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
    generate.add_argument(
        "--decoder-run",
        type=Path,
        help="torch-ema only: use the EMA decoder of a train_decoder_only run "
        "(step*.pt) in place of the checkpoint's decoder",
    )
    args = parser.parse_args()
    if args.command == "prepare":
        stft_overrides = {
            key: getattr(args, "reference_" + key)
            for key in REFERENCE_SPEC_DEFAULTS
            if getattr(args, "reference_" + key) is not None
        }
        if args.reference_spec and args.reference_frontend is None:
            prepare.error(
                "--reference-spec requires --reference-frontend (one of "
                f"{', '.join(sorted(REFERENCE_SPEC_FRONTENDS))}) matching the "
                "model's training cache builder"
            )
        if not args.reference_spec and (args.reference_frontend or stft_overrides):
            # 黙って無視すると「frontend を固定したつもり」の manifest になる
            prepare.error(
                "--reference-frontend / --reference-*-length require --reference-spec"
            )
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
                "frontend": args.reference_frontend,
                **stft_overrides,
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
        generate_audio(
            args.manifest,
            args.backend,
            args.output_dir,
            device=args.device,
            decoder_run=args.decoder_run,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
