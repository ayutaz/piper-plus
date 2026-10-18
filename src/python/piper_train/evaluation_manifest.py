"""Pinned inputs for audio generation and offline evaluation (no score imports)."""

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from piper_plus.embedding import validate_embedding

from .embedding_cache import atomic_write, file_sha256
from .reference_spec_contract import (
    REFERENCE_SPEC_FRONTENDS,
    frontend_steps,
    max_reference_frames,
    spec_array_sha256,
)


NORMALIZATION_VERSION = "nfkc-strip-PZS-v1"
BACKENDS = ("torch-raw", "torch-ema", "onnx")

# 参照 spec (F-mel、reference_conditioning="ref_spec") の STFT 設定の既定値。
# 学習 hparams (filter_length / hop_length / win_length) の既定と同じ契約値。
# frontend は既定値を持たない (モデルが学習した cache の作り方で決まる、R14)
REFERENCE_SPEC_DEFAULTS = {"filter_length": 1024, "hop_length": 256, "win_length": 1024}
_REFERENCE_SPEC_SETTINGS_KEYS = {
    "frontend",
    *REFERENCE_SPEC_DEFAULTS,
    "center",
    "spec_channels",
}
_REFERENCE_SPEC_RECORD_KEYS = {"audio_sha256", "spec_sha256", "frames", "spec_path"}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _is_int(value) -> bool:
    return type(value) is int


def reference_spec_settings(params: dict) -> dict:
    """manifest 最上位の ``reference_spec`` (frontend + STFT 設定) を作り検査する。

    ``params`` は ``frontend`` (必須、``REFERENCE_SPEC_FRONTENDS`` の閉じた集合)
    と ``REFERENCE_SPEC_DEFAULTS`` の一部の上書き (未知の key は拒否)。
    """
    allowed = {"frontend", *REFERENCE_SPEC_DEFAULTS}
    if not isinstance(params, dict) or set(params) - allowed:
        raise ValueError(
            f"reference_spec accepts only {sorted(allowed)}, got {params!r}"
        )
    if "frontend" not in params:
        raise ValueError(
            "reference_spec requires an explicit frontend (one of "
            f"{sorted(REFERENCE_SPEC_FRONTENDS)}) matching the model's training "
            "cache builder"
        )
    params = {**REFERENCE_SPEC_DEFAULTS, **params}
    settings = {
        "frontend": params["frontend"],
        **{key: params[key] for key in REFERENCE_SPEC_DEFAULTS},
        "center": False,
        "spec_channels": None,
    }
    if _is_int(settings["filter_length"]):
        settings["spec_channels"] = settings["filter_length"] // 2 + 1
    _validate_reference_spec_settings(settings)
    return settings


def _validate_reference_spec_settings(settings: dict) -> None:
    if not isinstance(settings, dict) or set(settings) != _REFERENCE_SPEC_SETTINGS_KEYS:
        raise ValueError("Invalid reference_spec settings keys")
    frontend_steps(settings["frontend"])
    if settings["center"] is not False:
        raise ValueError("reference_spec must use center=False")
    filter_length = settings["filter_length"]
    hop_length = settings["hop_length"]
    win_length = settings["win_length"]
    if not _is_int(filter_length) or filter_length < 2 or filter_length % 2:
        raise ValueError(
            f"reference_spec filter_length must be an even int, got {filter_length!r}"
        )
    if not _is_int(hop_length) or hop_length <= 0:
        raise ValueError(
            f"reference_spec hop_length must be a positive int, got {hop_length!r}"
        )
    if not _is_int(win_length) or not 0 < win_length <= filter_length:
        raise ValueError(
            "reference_spec win_length must be an int in (0, filter_length], "
            f"got {win_length!r}"
        )
    if settings["spec_channels"] != filter_length // 2 + 1:
        raise ValueError(
            "reference_spec spec_channels must be filter_length // 2 + 1 "
            f"({filter_length // 2 + 1}), got {settings['spec_channels']!r}"
        )


def compute_reference_spec(reference_path, settings: dict, sample_rate: int):
    """manifest の設定で参照 WAV から spec を作る (prepare と generate の共通経路)。

    Returns:
        (spec ``[filter_length // 2 + 1, T_ref]`` float32 torch.Tensor,
        clip 記録 ``{audio_sha256, spec_sha256, frames}``)。
    """
    from .reference_frontend import (  # noqa: PLC0415 — torch を遅延 import
        reference_spec_from_file,
        reference_spec_sha256,
    )

    spec, info = reference_spec_from_file(
        reference_path,
        target_sample_rate=sample_rate,
        filter_length=settings["filter_length"],
        hop_length=settings["hop_length"],
        win_length=settings["win_length"],
        frontend=settings["frontend"],
    )
    record = {
        "audio_sha256": file_sha256(Path(reference_path)),
        "spec_sha256": reference_spec_sha256(spec),
        "frames": info["frames"],
    }
    return spec, record


def reference_spec_dir(manifest_path: Path) -> Path:
    """prepare で固定した参照 spec (.npy) の置き場 (manifest の隣)。"""
    manifest_path = Path(manifest_path)
    return manifest_path.with_name(f"{manifest_path.stem}.reference_spec")


def load_reference_spec(clip: dict, settings: dict) -> np.ndarray:
    """prepare で保存した参照 spec を読み、manifest の固定値と照合して返す。

    Returns:
        ``[spec_channels, frames]`` float32 (C 順)。

    Raises:
        ValueError: 欠落・dtype/shape 違い・非有限・負値・hash 不一致。
    """
    tid = clip["id"]
    record = clip["reference_spec"]
    path = Path(record["spec_path"])
    try:
        spec = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"Missing/unreadable reference spec file for {tid}: {path}"
        ) from exc
    if spec.dtype != np.float32:
        raise ValueError(
            f"reference spec file for {tid} must be float32, got {spec.dtype}: {path}"
        )
    expected_shape = (settings["spec_channels"], record["frames"])
    if spec.shape != expected_shape:
        raise ValueError(
            f"reference spec file shape for {tid} is {spec.shape}, the manifest "
            f"pins {expected_shape}: {path}"
        )
    if not np.isfinite(spec).all() or (spec < 0).any():
        raise ValueError(
            f"reference spec file for {tid} must be finite and non-negative: {path}"
        )
    if spec_array_sha256(spec) != record["spec_sha256"]:
        raise ValueError(f"reference spec file hash mismatch for {tid}: {path}")
    return np.ascontiguousarray(spec)


def _stored_spec_matches(path: Path, spec_sha256: str) -> bool:
    """``path`` に hash ``spec_sha256`` の float32 spec が既にあるか。"""
    try:
        stored = np.load(path, allow_pickle=False)
    except (OSError, ValueError):
        return False
    return stored.dtype == np.float32 and spec_array_sha256(stored) == spec_sha256


def _validate_reference_spec_records(manifest: dict, *, verify_files: bool) -> None:
    settings = manifest.get("reference_spec")
    records = [clip.get("reference_spec") for clip in manifest["clips"]]
    if settings is None:
        if any(record is not None for record in records):
            raise ValueError(
                "Clip reference_spec records require reference_spec settings"
            )
        return
    _validate_reference_spec_settings(settings)
    sample_rate = manifest["sample_rate"]
    if not _is_int(sample_rate) or sample_rate <= 0:
        raise ValueError("Invalid sample_rate")
    limit = max_reference_frames(sample_rate, settings["hop_length"])
    for clip, record in zip(manifest["clips"], records, strict=True):
        tid = clip["id"]
        if record is None:
            raise ValueError(f"Missing reference_spec record for {tid}")
        if not isinstance(record, dict) or set(record) != _REFERENCE_SPEC_RECORD_KEYS:
            raise ValueError(f"Invalid reference_spec record keys for {tid}")
        # 学習は 192 次元と spec を同じ参照発話 1 本から作るので、評価でも
        # 1 本に限る (どの WAV の spec かを曖昧にしない)
        if len(clip["reference_audio"]) != 1:
            raise ValueError(
                f"reference_spec requires exactly one reference audio for {tid}, "
                f"got {len(clip['reference_audio'])}"
            )
        if record["audio_sha256"] != clip["reference_audio"][0]["sha256"]:
            raise ValueError(
                f"reference_spec audio_sha256 must pin the reference audio of {tid}"
            )
        if not isinstance(record["spec_sha256"], str) or not _SHA256_RE.fullmatch(
            record["spec_sha256"]
        ):
            raise ValueError(f"Invalid reference_spec spec_sha256 for {tid}")
        if not _is_int(record["frames"]) or not 1 <= record["frames"] <= limit:
            raise ValueError(
                f"Invalid reference_spec frames (T_ref) for {tid}: "
                f"{record['frames']!r} (limit {limit})"
            )
        if not isinstance(record["spec_path"], str) or not record["spec_path"]:
            raise ValueError(f"Invalid reference_spec spec_path for {tid}")
        if verify_files:
            load_reference_spec(clip, settings)


def _source_files() -> list[Path]:
    root = Path(__file__).resolve().parents[3]
    files = []
    for directory in (
        root / "src/python/piper_train",
        root / "src/python_run/piper_plus",
        root / "src/python/g2p/piper_plus_g2p",
    ):
        files.extend(directory.rglob("*.py"))
    files.extend(root.glob("pyproject.toml"))
    files.extend((root / "src").glob("*/pyproject.toml"))
    return sorted(files)


def inline_embedding_sha256(vector: list) -> str:
    return text_sha256(json.dumps(vector, separators=(",", ":")))


def clip_embedding(clip: dict, dimension: int) -> np.ndarray:
    value = clip.get("speaker_embedding")
    if value is None:
        value = np.load(clip["speaker_embedding_path"], allow_pickle=False)
    return validate_embedding(value, dimension)


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def conditions_sha256(manifest: dict) -> str:
    conditions = {
        key: value
        for key, value in manifest.items()
        if key not in ("models", "conditions_sha256")
    }
    return text_sha256(
        json.dumps(
            conditions, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    )


def _pin(path: Path) -> dict:
    path = path.resolve()
    try:
        return {"path": str(path), "sha256": file_sha256(path)}
    except OSError as exc:
        raise ValueError(f"Missing evaluation input: {path}") from exc


def _verify_file(item: dict) -> None:
    if _pin(Path(item["path"]))["sha256"] != item["sha256"]:
        raise ValueError(f"evaluation input hash mismatch: {item['path']}")


def validate_manifest(manifest: dict, *, verify_files: bool = True) -> dict:
    """Validate the serialized schema before any model/ASR is constructed."""
    try:
        if manifest["version"] != 1:
            raise ValueError("Unsupported evaluation manifest version")
        clips = manifest["clips"]
        if not isinstance(clips, list) or not clips:
            raise ValueError("Evaluation clips must not be empty")
        ids = set()
        dimension = manifest["embedding_dimension"]
        if type(dimension) is not int or dimension < 1:
            raise ValueError("Invalid embedding dimension")
        for clip in clips:
            tid = clip["id"]
            if (
                not isinstance(tid, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tid)
                or tid in ids
            ):
                raise ValueError(f"Invalid/duplicate clip ID: {tid}")
            ids.add(tid)
            if not isinstance(clip["text"], str) or not clip["text"].strip():
                raise ValueError(f"Empty text for {tid}")
            if clip["text_sha256"] != text_sha256(clip["text"]):
                raise ValueError(f"Text hash mismatch for {tid}")
            phonemes = clip["phoneme_ids"]
            if (
                not isinstance(phonemes, list)
                or not phonemes
                or any(type(value) is not int or value < 0 for value in phonemes)
            ):
                raise ValueError(f"Invalid phoneme_ids for {tid}")
            for field in ("language_id", "speaker_id"):
                if type(clip[field]) is not int or clip[field] < 0:
                    raise ValueError(f"Invalid {field} for {tid}")
            prosody = clip.get("prosody_features")
            if prosody is not None and (
                not isinstance(prosody, list)
                or len(prosody) != len(phonemes)
                or any(
                    item is not None
                    and (
                        not isinstance(item, dict)
                        or any(
                            type(item.get(key)) is not int for key in ("a1", "a2", "a3")
                        )
                    )
                    for item in prosody
                )
            ):
                raise ValueError(f"Invalid prosody_features for {tid}")
            inline = clip.get("speaker_embedding")
            if inline is not None:
                validate_embedding(inline, dimension)
                if inline_embedding_sha256(inline) != clip["speaker_embedding_sha256"]:
                    raise ValueError(f"Inline embedding hash mismatch for {tid}")
            if verify_files:
                if inline is None:
                    _verify_file(
                        {
                            "path": clip["speaker_embedding_path"],
                            "sha256": clip["speaker_embedding_sha256"],
                        }
                    )
                    clip_embedding(clip, dimension)
                for reference in clip["reference_audio"]:
                    _verify_file(reference)
        _validate_reference_spec_records(manifest, verify_files=verify_files)
        scales = manifest["scales"]
        if (
            not isinstance(scales, list)
            or len(scales) != 3
            or not np.isfinite(scales).all()
            or scales[0] < 0
            or scales[1] <= 0
            or scales[2] < 0
        ):
            raise ValueError("Invalid inference scales")
        if type(manifest["seed"]) is not int or not 0 <= manifest[
            "seed"
        ] <= 2**63 - len(clips):
            raise ValueError("Invalid inference seed")
        epoch = manifest.get("training_epoch")
        if epoch is not None and (type(epoch) is not int or epoch < 0):
            raise ValueError("Invalid training_epoch")
        source = manifest["source"]
        if not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", source["revision"]):
            raise ValueError("Source revision must be pinned")
        if not isinstance(source["files"], list) or not source["files"]:
            raise ValueError("Actual source files must be pinned")
        if type(manifest["sample_rate"]) is not int or manifest["sample_rate"] <= 0:
            raise ValueError("Invalid sample_rate")
        asr = manifest["asr"]
        if asr["normalization"] != NORMALIZATION_VERSION or not re.fullmatch(
            r"[a-fA-F0-9]{40}", asr["revision"]
        ):
            raise ValueError("ASR revision/normalization must be pinned")
        if any(
            not isinstance(asr[key], str) or not asr[key].strip()
            for key in ("model", "language")
        ):
            raise ValueError("Missing ASR model/language")
        if asr["device"] not in ("cuda", "cpu"):
            raise ValueError("Invalid ASR device")
        if (
            not isinstance(manifest["models"], dict)
            or not manifest["models"]
            or set(manifest["models"]) - set(BACKENDS)
        ):
            raise ValueError("Invalid evaluation backends")
        if manifest["conditions_sha256"] != conditions_sha256(manifest):
            raise ValueError("Evaluation conditions hash mismatch")
        if verify_files:
            for model in manifest["models"].values():
                _verify_file(model)
            source = manifest["source"]
            _verify_file(
                {"path": source["input_path"], "sha256": source["input_sha256"]}
            )
            _verify_file({"path": source["lock_path"], "sha256": source["lock_sha256"]})
            for implementation in source["files"]:
                _verify_file(implementation)
        return manifest
    except (KeyError, TypeError, AttributeError, OSError, OverflowError) as exc:
        raise ValueError(f"Invalid evaluation manifest: {exc}") from exc


def load_manifest(path: Path, *, verify_files: bool = True) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Evaluation manifest must be an object")
    return validate_manifest(manifest, verify_files=verify_files)


def create_manifest(
    *,
    source_path: Path,
    output_path: Path,
    models: dict[str, Path],
    sample_rate: int,
    asr_revision: str,
    source_revision: str,
    scales=(0.4, 1.0, 0.5),
    seed=42,
    asr_model="openai/whisper-small",
    asr_device="cuda",
    language="ja",
    dimension=192,
    lock_path: Path | None = None,
    training_epoch: int | None = None,
    reference_spec: dict | None = None,
) -> dict:
    """評価条件を固定した manifest を書く。

    ``reference_spec`` (opt-in、``{"frontend": <必須>, ...STFT の上書き}``) を
    渡すと、各 clip のただ 1 本の参照 WAV から名前付き frontend (学習 cache
    builder の写し) で参照 spec を作り、manifest の隣の
    ``<manifest stem>.reference_spec/<clip id>.<spec hash の先頭 16 桁>.npy`` に
    float32 で保存する (内容で名前が決まるので、やり直しの失敗が前の manifest の
    spec を壊さない)。
    manifest には frontend・STFT・参照音声 hash・spec hash (float32 bytes)・
    T_ref・保存先を記録する (ref_spec モデルの評価に必須。generate はこの
    保存 bytes を feed する)。既定 None の manifest は変更前と同じ schema。
    """
    source_path = Path(source_path).resolve()
    source = _pin(source_path)
    lock = _pin(
        Path(lock_path)
        if lock_path
        else Path(__file__).resolve().parents[3] / "uv.lock"
    )
    clips = []
    try:
        for line in source_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            inline = entry.get("speaker_embedding")
            if inline is not None:
                inline = validate_embedding(inline, dimension).tolist()
                embedding = {"path": None, "sha256": inline_embedding_sha256(inline)}
            else:
                embedding = _pin(source_path.parent / entry["speaker_embedding_path"])
                validate_embedding(
                    np.load(embedding["path"], allow_pickle=False), dimension
                )
            references = [
                _pin(source_path.parent / reference)
                for reference in entry.get("reference_audio_paths", [])
            ]
            clips.append(
                {
                    "id": entry["id"],
                    "text": entry["text"],
                    "text_sha256": text_sha256(entry["text"]),
                    "phoneme_ids": entry["phoneme_ids"],
                    "language_id": entry.get("language_id", 0),
                    "speaker_id": entry.get("speaker_id", 0),
                    "speaker_embedding_path": embedding["path"],
                    "speaker_embedding": inline,
                    "speaker_embedding_sha256": embedding["sha256"],
                    "reference_audio": references,
                    "prosody_features": entry.get("prosody_features"),
                }
            )
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError(f"Invalid evaluation source: {exc}") from exc
    settings = None
    specs = {}
    if reference_spec is not None:
        settings = reference_spec_settings(reference_spec)
        spec_dir = reference_spec_dir(Path(output_path).resolve())
        for clip in clips:
            if not clip["reference_audio"]:
                raise ValueError(
                    f"reference_spec requires reference audio for {clip['id']}"
                )
            if len(clip["reference_audio"]) != 1:
                raise ValueError(
                    "reference_spec requires exactly one reference audio for "
                    f"{clip['id']}, got {len(clip['reference_audio'])}"
                )
            path = clip["reference_audio"][0]["path"]
            try:
                spec, record = compute_reference_spec(path, settings, sample_rate)
            except ValueError as exc:
                raise ValueError(f"{exc} (clip {clip['id']}: {path})") from exc
            # 内容で名前を決める (spec hash の先頭 16 桁)。同じ output への prepare
            # のやり直しが別 frontend で失敗しても、前の manifest が pin する
            # 別 bytes の file を上書きしない
            spec_path = spec_dir / f"{clip['id']}.{record['spec_sha256'][:16]}.npy"
            clip["reference_spec"] = {**record, "spec_path": str(spec_path)}
            specs[spec_path] = spec.detach().cpu().numpy()
    manifest = {
        "version": 1,
        "source": {
            "revision": source_revision,
            "input_path": source["path"],
            "input_sha256": source["sha256"],
            "lock_path": lock["path"],
            "lock_sha256": lock["sha256"],
            "files": [_pin(path) for path in _source_files()],
        },
        "sample_rate": sample_rate,
        "embedding_dimension": dimension,
        "scales": list(scales),
        "seed": seed,
        "training_epoch": training_epoch,
        "asr": {
            "model": asr_model,
            "revision": asr_revision,
            "language": language,
            "device": asr_device,
            "normalization": NORMALIZATION_VERSION,
        },
        "clips": clips,
        "models": {backend: _pin(Path(path)) for backend, path in models.items()},
    }
    if settings is not None:
        # 既定 (None) では key 自体を作らない (旧 manifest と同じ schema・hash)
        manifest["reference_spec"] = settings
    manifest["conditions_sha256"] = conditions_sha256(manifest)
    # 参照 spec は全 clip の計算が成功してから書く。manifest の検証・書き込みが
    # 失敗したら、今回書いた spec だけを消す (manifest の無い spec を残さない)。
    # 同名で同じ hash の file が既にあれば、前の manifest が pin している同じ
    # bytes なので書き直さず、失敗しても消さない。
    # schema の誤りは spec を 1 つも書かないうちに止める
    validate_manifest(manifest, verify_files=False)
    written = []
    try:
        for spec_path, array in specs.items():
            if _stored_spec_matches(spec_path, spec_array_sha256(array)):
                continue
            atomic_write(
                spec_path,
                lambda target, array=array: np.save(target, array, allow_pickle=False),
            )
            written.append(spec_path)
        validate_manifest(manifest)
        atomic_write(
            Path(output_path),
            lambda target: target.write(
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            ),
        )
    except BaseException:
        for spec_path in written:
            spec_path.unlink(missing_ok=True)
        raise
    return manifest
