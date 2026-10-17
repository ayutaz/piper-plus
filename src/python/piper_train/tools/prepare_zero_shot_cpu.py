"""Pinned CPU-only reference experiment, model baseline and listening artifact.

Run stages separately: references -> export -> generate -> evaluate -> html.
The spec contains local trusted paths; no GPU allocation or training occurs.
Outputs must be new. Existing completed outputs are reused only after hash checks.
"""

import argparse
import gc
import html
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ..embedding_cache import atomic_write, file_sha256
from ..evaluation_manifest import create_manifest, load_manifest
from .cpu_reference_comparison import (
    crop_active_frames,
    independent_reals,
    load_native_ecapa,
    native_ecapa_embedding,
    reference_embedding,
)


def write_json(path, value):
    atomic_write(
        Path(path),
        lambda stream: stream.write(
            json.dumps(value, ensure_ascii=False, indent=2).encode()
        ),
    )


def pin(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": file_sha256(path)}


def verify_pin(item):
    if file_sha256(Path(item["path"])) != item["sha256"]:
        raise ValueError(f"artifact changed: {item['path']}")


def session(path):
    import onnxruntime as ort  # noqa: PLC0415

    from ..ort_utils import create_session_options  # noqa: PLC0415

    return ort.InferenceSession(
        str(path),
        sess_options=create_session_options(intra_op_threads=1),
        providers=["CPUExecutionProvider"],
    )


def prepare_references(spec, root):
    import soundfile as sf  # noqa: PLC0415
    import soxr  # noqa: PLC0415

    from ..infer_onnx import text_to_phoneme_ids_and_prosody  # noqa: PLC0415

    target = root / "references"
    if target.exists():
        raise ValueError(f"reference output already exists: {target}")
    target.mkdir(parents=True)
    sources = [Path(path).resolve() for path in spec["reference_sources"]]
    if len(sources) != 2:
        raise ValueError("controlled comparison requires exactly two source utterances")
    crops = {}
    crop_records = {}
    # 4.8 seconds active in single vs 2.4 + 2.4 seconds active in multi.
    count = spec.get("single_active_frames", 240)
    if count % 2:
        raise ValueError("single_active_frames must be divisible by two")
    for label, selected, active in [
        ("single", sources[:1], count),
        ("multi", sources, count // 2),
    ]:
        crops[label], crop_records[label] = [], []
        for ordinal, path in enumerate(selected):
            audio, rate = sf.read(path, dtype="float32", always_2d=True)
            audio = audio.mean(axis=1)
            if rate != 16000:
                audio = soxr.resample(audio, rate, 16000, quality="HQ")
            crop, metadata = crop_active_frames(audio, 16000, active)
            output = target / f"{label}-{ordinal}.wav"
            sf.write(output, crop, 16000, subtype="FLOAT")
            crops[label].append(output)
            crop_records[label].append(
                {
                    "source": pin(path),
                    "crop": pin(output),
                    **metadata,
                    "resampler": "soxr-HQ to 16000; stereo mean; no gain adjustment",
                }
            )
    encoder = session(spec["campplus"])
    variants = {}
    vectors = {}
    for kind, paths in crops.items():
        for mode, frames in [("whole", 0), ("chunks400", 400)]:
            name = f"{kind}-{mode}"
            vector, chunks = reference_embedding(encoder, paths, chunk_frames=frames)
            output = target / f"{name}.npy"
            np.save(output, vector, allow_pickle=False)
            vectors[name] = vector
            variants[name] = {
                "embedding": pin(output),
                "references": [pin(p) for p in paths],
                "source_utterances": [pin(p) for p in sources[: len(paths)]],
                "chunks_per_utterance": chunks,
                "pooling": "chunk-L2/mean/L2 then utterance-mean/L2"
                if frames
                else "whole-L2 then utterance-mean/L2",
                "chunk_frames": frames,
            }
    reals = independent_reals(
        [Path(p) for p in spec["cross_real_candidates"]],
        sources + [p for paths in crops.values() for p in paths],
    )
    if len(reals) < 2:
        raise ValueError("need two independent real utterances after source exclusion")
    real_vectors = np.stack([reference_embedding(encoder, [p])[0] for p in reals])
    floors = independent_reals(
        [Path(p) for p in spec["floor_candidates"]], sources + reals
    )
    if not floors:
        raise ValueError("no independent floor speaker candidates")
    floor_scores = [
        float(np.mean(real_vectors @ reference_embedding(encoder, [p])[0]))
        for p in floors
    ]
    floor = floors[int(np.argmax(floor_scores))]
    config = json.loads(Path(spec["config"]).read_text(encoding="utf-8"))
    texts = []
    for line in Path(spec["texts"]).read_text(encoding="utf-8").splitlines():
        tid, text = line.split("\t", 1)
        ids, prosody = text_to_phoneme_ids_and_prosody(
            text,
            config["phoneme_id_map"],
            language="ja",
            language_id_map=config["language_id_map"],
        )
        if not ids or max(ids) >= spec["num_symbols"]:
            raise ValueError("G2P symbols incompatible with checkpoints")
        texts.append(
            {
                "id": tid,
                "text": text,
                "phoneme_ids": ids,
                "prosody_features": prosody,
                "language_id": config["language_id_map"]["ja"],
            }
        )
    if len(texts) < 3:
        raise ValueError("baseline requires at least three evaluation texts")
    for name, variant in variants.items():
        path = target / f"{name}.jsonl"
        rows = [
            {
                **t,
                "speaker_embedding_path": variant["embedding"]["path"],
                "reference_audio_paths": [p["path"] for p in variant["references"]],
            }
            for t in texts
        ]
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        variant["evaluation_input"] = pin(path)
    report = {
        "version": 1,
        "encoder": pin(spec["campplus"]),
        "crops": crop_records,
        "variants": variants,
        "cross_reals": [pin(p) for p in reals],
        "floor": pin(floor),
        "floor_candidates": [
            {**pin(p), "campplus_similarity": s}
            for p, s in zip(floors, floor_scores, strict=True)
        ],
        "floor_selection": "highest mean CAM++ similarity among available Japanese other-speaker candidates; fixed before synth evaluation; not population-calibrated",
        "pairwise_embedding_cosine": {
            a: {b: float(x @ y) for b, y in vectors.items()} for a, x in vectors.items()
        },
        "scope": "one Japanese target speaker; RMS activity proxy, not phonetic voiced duration",
    }
    write_json(root / "references.json", report)
    return report


def fresh_export(spec, model, root, references):
    import onnx  # noqa: PLC0415
    import torch  # noqa: PLC0415

    from ..export_onnx import (  # noqa: PLC0415
        OPSET_VERSION,
        apply_ema_scope_from_checkpoint,
        build_infer_forward,
    )
    from ..inference_eval import isolated_inference  # noqa: PLC0415
    from .generate_eval_audio import load_torch_generator  # noqa: PLC0415

    directory = root / "fresh-onnx"
    directory.mkdir(exist_ok=True)
    path = directory / (model["id"] + ".onnx")
    receipt = path.with_suffix(".json")
    checkpoint = pin(model["checkpoint"])
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding="utf-8"))
        verify_pin(record["onnx"])
        for item in record["source_files"]:
            verify_pin(item)
        if record["checkpoint"] != checkpoint:
            raise ValueError("export checkpoint changed")
        return record
    if path.exists():
        raise ValueError(f"partial export requires inspection: {path}")
    generator, state, rate = load_torch_generator(model["checkpoint"], device="cpu")
    if state["epoch"] != model["epoch"] or rate != 22050:
        raise ValueError("checkpoint epoch/sample rate mismatch")
    ema = apply_ema_scope_from_checkpoint(generator, state)
    if not ema or any(applied == 0 or skipped for applied, skipped in ema.values()):
        raise ValueError("incompatible EMA cannot be exported as EMA")
    del state
    clip = json.loads(
        Path(references["variants"]["single-whole"]["evaluation_input"]["path"])
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    text = torch.tensor([clip["phoneme_ids"]], dtype=torch.long)
    embedding = torch.from_numpy(
        np.load(references["variants"]["single-whole"]["embedding"]["path"])
    )[None, :]
    prosody = torch.tensor(
        [
            [
                [p["a1"], p["a2"], p["a3"]] if p else [0, 0, 0]
                for p in clip["prosody_features"]
            ]
        ],
        dtype=torch.long,
    )
    args = (
        text,
        torch.tensor([text.shape[1]]),
        torch.tensor(spec["scales"]),
        embedding,
        torch.tensor([clip["language_id"]]),
        prosody,
    )
    with isolated_inference(generator, spec["seed"]):
        generator.dec.remove_weight_norm()
        generator.forward = build_infer_forward(generator, stochastic=True)
        generator(*args)
        torch.onnx.export(
            generator,
            args,
            str(path),
            opset_version=OPSET_VERSION,
            dynamo=False,
            input_names=[
                "input",
                "input_lengths",
                "scales",
                "speaker_embedding",
                "lid",
                "prosody_features",
            ],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "speaker_embedding": {0: "batch_size"},
                "lid": {0: "batch_size"},
                "prosody_features": {0: "batch_size", 1: "phonemes"},
                "output": {0: "batch_size", 2: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
        )
    graph = onnx.load(path)
    onnx.checker.check_model(graph)
    onnx.shape_inference.infer_shapes(graph)
    ort_session = session(path)
    feeds = {
        item.name: tensor.numpy()
        for item, tensor in zip(ort_session.get_inputs(), args, strict=True)
    }
    audio = ort_session.run(["output"], feeds)[0]
    if not audio.size or not np.isfinite(audio).all():
        raise ValueError("fresh ONNX did not produce a valid waveform")
    from ..evaluation_manifest import _source_files  # noqa: PLC0415

    record = {
        "checkpoint": checkpoint,
        "onnx": pin(path),
        "epoch": model["epoch"],
        "weights": "existing checkpoint EMA",
        "ema_applied": ema,
        "device": "cpu / CPUExecutionProvider",
        "source_revision": spec["source_revision"],
        "source_files": [pin(p) for p in _source_files()],
        "opset": OPSET_VERSION,
        "stochastic": True,
        "checker": "passed",
        "shape_inference": "passed",
        "smoke_samples": int(audio.size),
    }
    write_json(receipt, record)
    del generator, ort_session, graph
    gc.collect()
    return record


def evaluation_jobs(spec):
    for model in spec["models"]:
        for backend in ("torch-raw", "torch-ema", "onnx"):
            yield model, "single-whole", backend
    selected = next(
        m for m in spec["models"] if m["id"] == spec["reference_comparison_model"]
    )
    for variant in ("single-chunks400", "multi-whole", "multi-chunks400"):
        yield selected, variant, "torch-raw"


def generate(spec, root, references):
    from .generate_eval_audio import generate_audio  # noqa: PLC0415

    (root / "manifests").mkdir(exist_ok=True)
    for model, variant, backend in evaluation_jobs(spec):
        label = f"{model['id']}-{variant}"
        manifest_path = root / "manifests" / (label + ".json")
        if not manifest_path.exists():
            create_manifest(
                source_path=Path(
                    references["variants"][variant]["evaluation_input"]["path"]
                ),
                output_path=manifest_path,
                models={
                    "torch-raw": Path(model["checkpoint"]),
                    "torch-ema": Path(model["checkpoint"]),
                    "onnx": root / "fresh-onnx" / (model["id"] + ".onnx"),
                },
                sample_rate=22050,
                asr_revision=spec["asr_revision"],
                source_revision=spec["source_revision"],
                asr_device="cpu",
                training_epoch=model["epoch"],
                scales=spec["scales"],
                seed=spec["seed"],
            )
        else:
            load_manifest(manifest_path)
        directory = root / "audio" / label / backend
        if (directory / "generation.json").exists():
            # The strict CER validator also verifies all WAV hashes and metadata.
            from .eval_cer import _strict_inputs  # noqa: PLC0415

            _strict_inputs(cer_arguments(manifest_path, directory))
        else:
            print(f"GENERATE {label} {backend}", flush=True)
            generate_audio(manifest_path, backend, directory, device="cpu")
        gc.collect()


def cer_arguments(manifest_path, directory):
    return SimpleNamespace(
        manifest=str(manifest_path),
        clips_dir=str(directory),
        asr_model=None,
        asr_revision=None,
        language=None,
        asr_device="cpu",
        texts=None,
    )


def evaluate(spec, root, references):
    from .eval_cer import _evaluate_strict  # noqa: PLC0415
    from .eval_zs_secs import (  # noqa: PLC0415
        compute_acoustics_blocks,
        compute_secs_report,
    )

    encoder = session(spec["campplus"])
    native = load_native_ecapa(spec["ecapa_directory"])
    ecapa_source = Path(spec["ecapa_directory"])
    native_pins = [
        pin(ecapa_source / name)
        for name in ("hyperparams.yaml", "embedding_model.ckpt")
    ]
    cache = {}

    def embeddings(paths, name):
        results = []
        for path in paths:
            key = (file_sha256(path), name)
            if key not in cache:
                cache[key] = (
                    reference_embedding(encoder, [path])[0]
                    if name == "campplus"
                    else native_ecapa_embedding(native, path)
                )
            results.append(cache[key])
        return np.stack(results)

    reals = [Path(p["path"]) for p in references["cross_reals"]]
    floors = [Path(references["floor"]["path"])]
    groups = []
    for model, variant, backend in evaluation_jobs(spec):
        label = f"{model['id']}-{variant}"
        directory = root / "audio" / label / backend
        manifest_path = root / "manifests" / (label + ".json")
        manifest = load_manifest(manifest_path)
        result_path = directory / "metrics.json"
        if result_path.exists():
            record = json.loads(result_path.read_text(encoding="utf-8"))
            if record["generation_sha256"] != file_sha256(
                directory / "generation.json"
            ):
                raise ValueError("evaluated generation changed")
            for item in record["pinned_inputs"]:
                verify_pin(item)
            if record["manifest_sha256"] != file_sha256(manifest_path):
                raise ValueError("evaluated manifest changed")
            groups.append(record)
            continue
        print(f"EVALUATE {label} {backend}", flush=True)
        cer, exit_code = _evaluate_strict(cer_arguments(manifest_path, directory))
        write_json(directory / "cer.json", {**cer, "exit_code": exit_code})
        if exit_code == 2 or cer.get("failed_clips"):
            raise ValueError(f"strict CER execution failed: {cer}")
        synth = [directory / (clip["id"] + ".wav") for clip in manifest["clips"]]
        conditions = [
            Path(p["path"]) for p in references["variants"][variant]["references"]
        ]
        source_utts = [
            Path(p["path"])
            for p in references["variants"][variant]["source_utterances"]
        ]
        if independent_reals(reals, conditions + source_utts) != reals:
            raise ValueError("conditioning utterance leaked into real evaluation set")
        all_inputs = synth + reals + floors + conditions + source_utts
        scores = {}
        for name in ("campplus", "ecapa-native"):
            ref = embeddings(conditions, name).mean(axis=0)
            ref /= np.linalg.norm(ref)
            scores[name] = compute_secs_report(
                embeddings(synth, name),
                embeddings(reals, name),
                ref_emb=ref,
                floor_embs=embeddings(floors, name),
            )
        band, comb, prosody, comb_hnr = compute_acoustics_blocks(synth, reals)
        record = {
            "model": model["id"],
            "variant": variant,
            "backend": backend,
            "manifest_sha256": file_sha256(manifest_path),
            "conditions_sha256": manifest["conditions_sha256"],
            "generation_sha256": file_sha256(directory / "generation.json"),
            "directory": str(directory.resolve()),
            "cer": cer,
            "cer_gate_exit": exit_code,
            "encoders": scores,
            "band": band,
            "comb": comb,
            "prosody": prosody,
            "comb_hnr": comb_hnr,
            "pinned_inputs": [pin(p) for p in all_inputs]
            + [pin(spec["campplus"])]
            + native_pins,
            "ecapa": {
                "revision": spec["ecapa_revision"],
                "frontend": "native SpeechBrain waveform encode_batch(normalize=False), soundfile mono, soxr-HQ 16kHz",
                "device": "cpu",
            },
            "scope": "Japanese single-speaker diagnostic; not human quality acceptance",
        }
        write_json(result_path, record)
        groups.append(record)
        gc.collect()
    write_json(
        root / "baseline.json",
        {
            "version": 1,
            "spec": pin(root / "experiment.json"),
            "references": pin(root / "references.json"),
            "groups": groups,
            "source_revision": spec["source_revision"],
            "cpu_only": True,
            "comparison_policy": "same texts/reference/scales/seed for baselines; epoch/model deliberately differ; ONNX uses EMA; independent Torch/ORT RNG streams are not waveform-identical",
        },
    )


def listening_html(root):
    report = json.loads((root / "baseline.json").read_text(encoding="utf-8"))
    references = json.loads((root / "references.json").read_text(encoding="utf-8"))

    def player(path):
        relative = Path(os.path.relpath(path, root)).as_posix()
        return f'<audio controls preload="none" src="{html.escape(relative, quote=True)}"></audio>'

    blocks = []
    for label, records in references["crops"].items():
        blocks.append(
            f"<p>{html.escape(label)} "
            + " ".join(player(r["crop"]["path"]) for r in records)
            + "</p>"
        )
    rows = []
    for record in report["groups"]:
        directory = Path(record["directory"])
        generation = json.loads(
            (directory / "generation.json").read_text(encoding="utf-8")
        )
        scores = record["encoders"]
        title = html.escape(
            " / ".join(record[k] for k in ("model", "variant", "backend"))
        )
        values = [
            f"{scores[name]['normalized_transfer']:.3f}"
            if scores[name]["normalized_transfer"] is not None
            else "undefined"
            for name in ("campplus", "ecapa-native")
        ]
        cells = "".join(
            f"<td>{html.escape(c['id'])}{player(directory / (c['id'] + '.wav'))}</td>"
            for c in generation["clips"]
        )
        rows.append(
            f"<tr><th>{title}<br>CER {record['cer']['cer_median']:.3f}<br>Transfer CAM++ / ECAPA: {' / '.join(values)}</th>{cells}</tr>"
        )
    content = (
        """<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Zero-Shot CPU comparison</title>
<style>body{font:16px sans-serif;margin:24px;background:#fafafa;color:#222}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:12px;text-align:left}audio{display:block;width:280px;margin:8px 0}th{max-width:330px;font-weight:normal}p{max-width:960px;line-height:1.6}</style>
<h1>Zero-Shot CPU基準評価</h1><p>つくよみちゃん1話者・3文の診断です。新たな学習や人手による品質合格判定は実施していません。ONNXは既存EMAを現行コードで新規export。v11 ep9/ep19はepoch条件により昇格対象外です。音量補正・無音除去をしていない生成音声です。参照の音声量は20ms RMS活動フレームで一致させています（言語的な有声時間の保証ではありません）。</p>
<p>確認点：声の似方、読み間違い、金属音・ざらつき、不自然な音高、語尾や無音の異常。指標の大小だけで採用しないでください。</p><h2>参照音声</h2>"""
        + "".join(blocks)
        + "<h2>生成音声</h2><div style='overflow:auto'><table>"
        + "".join(rows)
        + "</table></div><p><a href='baseline.json'>評価JSON</a> / <a href='references.json'>参照条件・SHA256</a> / <a href='experiment.json'>実験設定</a></p></html>"
    )
    (root / "index.html").write_text(content, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--stage",
        choices=("references", "export", "generate", "evaluate", "html"),
        required=True,
    )
    args = parser.parse_args(argv)
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import torch  # noqa: PLC0415

    torch.set_num_threads(1)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if revision != spec["source_revision"]:
        raise ValueError("source revision differs from experiment spec")
    frozen = root / "experiment.json"
    if frozen.exists() and json.loads(frozen.read_text(encoding="utf-8")) != spec:
        raise ValueError("experiment spec changed; use a new output directory")
    write_json(frozen, spec)
    if args.stage == "references":
        prepare_references(spec, root)
    elif args.stage == "html":
        listening_html(root)
    else:
        references = json.loads((root / "references.json").read_text(encoding="utf-8"))
        for variant in references["variants"].values():
            for item in [
                variant["embedding"],
                variant["evaluation_input"],
                *variant["references"],
                *variant["source_utterances"],
            ]:
                verify_pin(item)
        for item in references["cross_reals"] + [
            references["floor"],
            references["encoder"],
        ]:
            verify_pin(item)
        if args.stage == "export":
            for model in spec["models"]:
                print(f"EXPORT {model['id']}", flush=True)
                fresh_export(spec, model, root, references)
        elif args.stage == "generate":
            generate(spec, root, references)
        else:
            evaluate(spec, root, references)
    print(f"CPU_STAGE_COMPLETE {args.stage}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
