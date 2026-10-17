"""Read-only artifact, dataset and embedding-provenance audit for CPU preparation."""

import argparse
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
from google.protobuf.message import DecodeError

from piper_plus.embedding import validate_embedding

from ..embedding_cache import atomic_write, file_sha256, read_verified


def audit_artifacts(specifications):
    results = []
    for spec in specifications:
        path = Path(spec["path"]).resolve()
        result = {**spec, "path": str(path), "status": "missing"}
        if path.is_file():
            result.update(bytes=path.stat().st_size, sha256=file_sha256(path))
            try:
                if result["bytes"] == 0:
                    raise ValueError("empty artifact")
                kind = spec.get("kind", "file")
                if kind == "embedding":
                    vector = np.load(path, allow_pickle=False)
                    validate_embedding(vector, spec.get("dimension", 192))
                    result.update(
                        shape=list(vector.shape), norm=float(np.linalg.norm(vector))
                    )
                elif kind == "onnx":
                    import onnx  # noqa: PLC0415 - optional artifact inspection backend.

                    model = onnx.load(path, load_external_data=False)
                    result["inputs"] = [
                        {
                            "name": item.name,
                            "shape": [
                                d.dim_param or d.dim_value
                                for d in item.type.tensor_type.shape.dim
                            ],
                        }
                        for item in model.graph.input
                    ]
                    result["outputs"] = [item.name for item in model.graph.output]
                    external = []
                    for tensor in model.graph.initializer:
                        for entry in tensor.external_data:
                            if entry.key != "location":
                                continue
                            dependency = (path.parent / entry.value).resolve()
                            if (
                                not dependency.is_relative_to(path.parent)
                                or not dependency.is_file()
                            ):
                                raise ValueError("missing or unsafe ONNX external data")
                            if not any(
                                item["path"] == str(dependency) for item in external
                            ):
                                external.append(
                                    {
                                        "path": str(dependency),
                                        "sha256": file_sha256(dependency),
                                    }
                                )
                    result["external_data"] = external
                elif kind == "checkpoint":
                    if not spec.get("trusted_checkpoint"):
                        raise ValueError(
                            "checkpoint inspection requires an explicitly trusted local source"
                        )
                    from ..checkpoint_io import load_checkpoint  # noqa: PLC0415

                    checkpoint = load_checkpoint(path)
                    hparams = checkpoint["hyper_parameters"]
                    keys = (
                        "num_symbols",
                        "num_speakers",
                        "num_languages",
                        "sample_rate",
                        "use_zero_shot",
                        "segment_size",
                        "ema_scope",
                        "spk_loss_type",
                        "spk_loss_positives",
                    )
                    result.update(
                        epoch=checkpoint.get("epoch"),
                        global_step=checkpoint.get("global_step"),
                        hparams={key: hparams.get(key) for key in keys},
                        ema_keys=[key for key in checkpoint if "ema" in key],
                    )
                    del checkpoint
                elif kind == "json":
                    json.loads(path.read_text(encoding="utf-8"))
                elif kind == "wav":
                    import soundfile as sf  # noqa: PLC0415

                    audio, rate = sf.read(path, dtype="float32")
                    if not len(audio) or not np.isfinite(audio).all():
                        raise ValueError("invalid or empty WAV")
                    result.update(
                        sample_rate=rate, frames=len(audio), duration=len(audio) / rate
                    )
                elif kind != "file":
                    raise ValueError(f"unknown artifact kind: {kind}")
                if spec.get("expected_sha256") not in (None, result["sha256"]):
                    raise ValueError("artifact SHA256 mismatch")
                result["status"] = "verified"
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                RuntimeError,
                EOFError,
                DecodeError,
            ) as error:
                result.update(status="invalid", error=str(error))
        results.append(result)
    return results


def audit_datasets(specifications, *, encoder_sha256=None, progress_every=0):
    datasets = []
    speakers = {"train": set(), "holdout": set()}
    audio_hashes = {"train": set(), "holdout": set()}
    hash_cache = {}
    parent_exists = {}

    def is_file(path):
        if path is None:
            return False
        if path.parent not in parent_exists:
            parent_exists[path.parent] = path.parent.is_dir()
        return parent_exists[path.parent] and path.is_file()

    for spec in specifications:
        manifest = Path(spec["path"]).resolve()
        missing = Counter()
        result = {
            **spec,
            "path": str(manifest),
            "status": "missing",
            "records": 0,
            "invalid_records": 0,
            "embedding_invalid": 0,
            "embedding_unverified": 0,
            "missing_by_field": missing,
            "duplicate_audio_stems": 0,
            "examples": [],
        }
        stems = {}
        dataset_speakers = set()
        if manifest.is_file():
            result.update(status="audited", sha256=file_sha256(manifest))
            with manifest.open(encoding="utf-8") as source:
                for line_number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    result["records"] += 1
                    if progress_every and result["records"] % progress_every == 0:
                        print(
                            f"auditing {spec['id']}: {result['records']} records",
                            flush=True,
                        )
                    try:
                        row = json.loads(line)
                        ids = row["phoneme_ids"]
                        if (
                            not isinstance(ids, list)
                            or not ids
                            or any(type(i) is not int or i < 0 for i in ids)
                        ):
                            raise ValueError("invalid phoneme_ids")
                        if spec.get("num_symbols") and max(ids) >= spec["num_symbols"]:
                            raise ValueError("phoneme ID exceeds model num_symbols")
                        for field, maximum in (
                            ("speaker_id", "num_speakers"),
                            ("language_id", "num_languages"),
                        ):
                            if spec.get(maximum) and (
                                type(row.get(field)) is not int
                                or not 0 <= row[field] < spec[maximum]
                            ):
                                raise ValueError(f"{field} exceeds model {maximum}")
                        speaker = row.get("speaker")
                        if speaker is None:
                            speaker = row.get("speaker_id")
                        if speaker is None:
                            raise ValueError("missing speaker identity")
                        role = spec["role"]
                        dataset_speakers.add(str(speaker))
                        speakers.setdefault(role, set()).add(str(speaker))
                        if spec.get("f0_directory"):
                            from ..vits.dataset import PiperDataset  # noqa: PLC0415

                            f0_value = row.get("f0_path")
                            f0_path = (
                                Path(os.path.abspath(manifest.parent / f0_value))
                                if f0_value
                                else PiperDataset._f0_path_for(
                                    Path(spec["f0_directory"]),
                                    Path(row.get("audio_spec_path", "missing")),
                                )
                            )
                            if not is_file(f0_path):
                                missing["f0_path"] += 1
                        for field in (
                            "audio_path",
                            "audio_norm_path",
                            "audio_spec_path",
                            "speaker_embedding_path",
                        ):
                            value = row.get(field)
                            path = (
                                Path(os.path.abspath(manifest.parent / str(value)))
                                if value
                                else None
                            )
                            if not is_file(path):
                                missing[field] += 1
                                continue
                            if field == "audio_path":
                                if path not in hash_cache:
                                    hash_cache[path] = file_sha256(path)
                                audio_hashes.setdefault(role, set()).add(
                                    hash_cache[path]
                                )
                                if path.stem in stems and stems[path.stem] != path:
                                    result["duplicate_audio_stems"] += 1
                                stems[path.stem] = path
                            if field == "speaker_embedding_path":
                                try:
                                    validate_embedding(
                                        np.load(path, allow_pickle=False),
                                        spec.get("dimension", 192),
                                    )
                                except (OSError, ValueError, TypeError, EOFError):
                                    result["embedding_invalid"] += 1
                                    continue
                                expected = {
                                    "encoder_sha256": encoder_sha256,
                                    "dimension": spec.get("dimension", 192),
                                }
                                normalized = row.get("audio_norm_path")
                                normalized_path = (
                                    Path(os.path.abspath(manifest.parent / normalized))
                                    if normalized
                                    else None
                                )
                                if is_file(normalized_path):
                                    if normalized_path not in hash_cache:
                                        hash_cache[normalized_path] = file_sha256(
                                            normalized_path
                                        )
                                    expected["audio_sha256"] = hash_cache[
                                        normalized_path
                                    ]
                                try:
                                    metadata = json.loads(
                                        path.with_suffix(".json").read_text(
                                            encoding="utf-8"
                                        )
                                    )
                                except (OSError, ValueError):
                                    metadata = {}
                                required = {
                                    "version",
                                    "audio_sha256",
                                    "source_sr",
                                    "target_sr",
                                    "resampler",
                                    "fbank_version",
                                    "pooling",
                                }
                                if (
                                    not required.issubset(metadata)
                                    or "audio_sha256" not in expected
                                    or read_verified(path, expected) is None
                                ):
                                    result["embedding_unverified"] += 1
                    except (ValueError, TypeError, KeyError) as error:
                        result["invalid_records"] += 1
                        if len(result["examples"]) < 20:
                            result["examples"].append(
                                {"line": line_number, "error": str(error)}
                            )
            result["speakers"] = len(dataset_speakers)
        result["count_matches"] = (
            spec.get("expected_records", result["records"]) == result["records"]
        )
        datasets.append(result)
    overlap = sorted(speakers["train"] & speakers["holdout"])
    audio_overlap = sorted(audio_hashes["train"] & audio_hashes["holdout"])
    ready = bool(datasets) and any(s.get("role") == "train" for s in specifications)
    ready = (
        ready
        and not overlap
        and not audio_overlap
        and all(
            d["status"] == "audited"
            and d["records"] > 0
            and d["count_matches"]
            and d["invalid_records"] == 0
            and not any(d["missing_by_field"].values())
            and d["embedding_invalid"] == d["embedding_unverified"] == 0
            for d in datasets
        )
    )
    return {
        "datasets": datasets,
        "speaker_overlap": overlap,
        "audio_hash_overlap": audio_overlap,
        "audio_hash_overlap_fully_checked": bool(datasets)
        and all(
            d["records"] > 0
            and d["invalid_records"] == 0
            and d["status"] == "audited"
            and not d["missing_by_field"].get("audio_path", 0)
            for d in datasets
        ),
        "training_ready": bool(ready),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    artifacts = audit_artifacts(spec.get("artifacts", []))
    data = audit_datasets(
        spec.get("datasets", []),
        encoder_sha256=spec.get("encoder_sha256"),
        progress_every=50000,
    )
    report = {
        "version": 1,
        "source_revision": spec.get("source_revision"),
        "spec_sha256": file_sha256(args.spec),
        "artifacts": artifacts,
        **data,
    }
    report["training_ready"] = report["training_ready"] and all(
        item["status"] == "verified" for item in artifacts if item.get("required", True)
    )
    atomic_write(
        args.output,
        lambda stream: stream.write(
            json.dumps(report, ensure_ascii=False, indent=2).encode()
        ),
    )
    print(f"audit written: {args.output}; training_ready={report['training_ready']}")
    return 0 if report["training_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
