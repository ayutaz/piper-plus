"""S0 (reference-fusion plan) CPU measurement for the G0 frontend decision.

Stages (run in order, each resumable; never writes under the baseline dir):
  prepare       reference embeddings, eval JSONL and manifests  (main env)
  generate      CPU audio for every (condition, backend)        (main env)
  evaluate      strict CER + CAM++/native ECAPA cross-utt + acoustics
                (metrics overlay env, same evaluator as the baseline)
  separability  CAM++ 192 vs CAM++ pre-pooling stats 1024 same/other AUC
  summary       deltas and the mechanical G0 decisions

(a) trim:   v10b ep79 raw/EMA/ONNX; WAV001 as-is and WAV001 with 1 s of
            -60 dBFS noise padding on both sides; trim none vs energy-vad.
(b) average: v10b ep79 raw/EMA (Torch only); baseline multi crops;
            embedding-side L2(mean e_i) vs g-side mean spk_proj(e_i).
Baseline texts, seed, scales, ASR, cross-real 003-008 and the pinned floor
are reused read-only from the baseline ``comparison-final`` directory.
"""

import argparse
import gc
import json
import os
import subprocess
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "output/zero-shot-cpu-preparation-20261017/comparison-final"
TORCH_CAMPPLUS = (
    ROOT
    / "output/zero-shot-cpu-preparation-20261017/evaluation-models"
    / "campplus-torch/campplus_cn_common.bin"
)
MODEL_ID = "v10b-ep79"
TRIM_CONDITIONS = ("a-wav001", "a-wav001-pad")
AVERAGE_BACKENDS = ("torch-raw", "torch-ema")
ALL_BACKENDS = ("torch-raw", "torch-ema", "onnx")
PAD_SECONDS = 1.0
PAD_DBFS = -60.0
PAD_SEED = 20261017
STATS_AUC_MARGIN = 0.02
MOE_SPEECH = Path(
    os.environ.get(
        "S0_MOE_SPEECH_DIR",
        Path.home()
        / ".cache/huggingface/hub/datasets--ayousanz--moe-speech-20speakers-ljspeech"
        / "snapshots/6cd2b0902884d7da31e93cd7ee3444baf8fafb64",
    )
)
PER_SPEAKER = 10


def conditions():
    """(condition, backends, trim, kind) in evaluation order."""
    for name in TRIM_CONDITIONS:
        for trim in ("none", "energy-vad"):
            yield f"{name}-trim-{trim}", ALL_BACKENDS
    for average in ("embedding", "g"):
        yield f"b-multi-{average}-average", AVERAGE_BACKENDS


# ---------------------------------------------------------------- decisions


def trim_decision(cells):
    """Adopt trim only if every cell is non-regressing on all three metrics.

    ``cells``: list of dicts with ``campplus_delta``, ``ecapa_delta`` (trim
    minus none, cross-utt) and ``cer_delta`` (trim minus none, median) plus
    ``flags`` (Goodhart / above-ceiling booleans of the trim group).
    """
    failures = []
    for cell in cells:
        reasons = []
        if cell["campplus_delta"] < 0:
            reasons.append("CAM++ cross regressed")
        if cell["ecapa_delta"] < 0:
            reasons.append("ECAPA cross regressed")
        if cell["cer_delta"] > 0:
            reasons.append("CER median regressed")
        if any(cell["flags"].values()):
            reasons.append("Goodhart/above-ceiling flag")
        if reasons:
            failures.append({"cell": cell["cell"], "reasons": reasons})
    return {"adopt_trim": bool(cells) and not failures, "failures": failures}


def averaging_decision(cells):
    """Keep embedding-side unless g-side is better on both encoders, no CER loss."""
    failures = []
    for cell in cells:
        reasons = []
        if not cell["campplus_delta"] > 0:
            reasons.append("CAM++ cross not better")
        if not cell["ecapa_delta"] > 0:
            reasons.append("ECAPA cross not better")
        if cell["cer_delta"] > 0:
            reasons.append("CER median regressed")
        if any(cell["flags"].values()):
            reasons.append("Goodhart/above-ceiling flag")
        if reasons:
            failures.append({"cell": cell["cell"], "reasons": reasons})
    return {
        "position": "g" if cells and not failures else "embedding",
        "failures": failures,
    }


def stats_decision(stats, baseline, *, margin=STATS_AUC_MARGIN):
    """Fail only when stats are clearly worse than the 192-d embedding."""
    reasons = []
    if stats["auc"] < baseline["auc"] - margin:
        reasons.append(f"AUC lower by more than {margin}")
    if stats["gap"] < baseline["gap"]:
        reasons.append("same/other cosine gap smaller")
    return {
        "passes": not reasons,
        "reasons": reasons,
        "weak_evidence": stats["n_speakers"] < 10,
    }


# ---------------------------------------------------------------- helpers


def _prepare_module():
    from piper_train.tools import prepare_zero_shot_cpu  # noqa: PLC0415

    return prepare_zero_shot_cpu


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _baseline():
    prepare = _prepare_module()
    spec = _load_json(BASELINE / "experiment.json")
    references = _load_json(BASELINE / "references.json")
    for item in [
        references["floor"],
        references["encoder"],
        *references["cross_reals"],
        *[r["crop"] for r in references["crops"]["multi"]],
        references["variants"]["single-whole"]["evaluation_input"],
    ]:
        prepare.verify_pin(item)
    onnx_receipt = _load_json(BASELINE / "fresh-onnx" / f"{MODEL_ID}.json")
    prepare.verify_pin(onnx_receipt["onnx"])
    model = next(m for m in spec["models"] if m["id"] == MODEL_ID)
    return spec, references, model, onnx_receipt


def _texts(references):
    path = Path(references["variants"]["single-whole"]["evaluation_input"]["path"])
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row.pop("speaker_embedding_path")
        row.pop("reference_audio_paths")
        rows.append(row)
    return rows


def _padded_reference(source, target):
    import soundfile as sf  # noqa: PLC0415

    audio, rate = sf.read(source, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    rng = np.random.default_rng(PAD_SEED)
    amplitude = 10 ** (PAD_DBFS / 20)
    pad = int(PAD_SECONDS * rate)
    noise = (amplitude * rng.standard_normal((2, pad))).astype(np.float32)
    sf.write(target, np.concatenate([noise[0], audio, noise[1]]), rate, "FLOAT")
    return {"seconds_each_side": PAD_SECONDS, "rms_dbfs": PAD_DBFS, "seed": PAD_SEED}


# ---------------------------------------------------------------- stages


def stage_prepare(root):
    import soundfile as sf  # noqa: PLC0415

    from piper_train.evaluation_manifest import create_manifest  # noqa: PLC0415
    from piper_train.reference_frontend import trim_reference_audio  # noqa: PLC0415
    from piper_train.tools.cpu_reference_comparison import (  # noqa: PLC0415
        reference_embedding,
    )

    prepare = _prepare_module()
    spec, references, model, onnx_receipt = _baseline()
    target = root / "references"
    if (root / "references.json").exists():
        raise ValueError("prepare already completed; use a new output directory")
    target.mkdir(parents=True, exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    encoder = prepare.session(spec["campplus"])
    wav001, wav002 = (Path(p) for p in spec["reference_sources"])
    padded = target / "wav001-pad.wav"
    padding = _padded_reference(wav001, padded)
    sources = {"a-wav001": [wav001], "a-wav001-pad": [padded]}
    multi = [Path(r["crop"]["path"]) for r in references["crops"]["multi"]]
    texts = _texts(references)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    record = {
        "version": 1,
        "source_revision": revision,
        "baseline": {
            "experiment": prepare.pin(BASELINE / "experiment.json"),
            "references": prepare.pin(BASELINE / "references.json"),
            "fresh_onnx": onnx_receipt["onnx"],
            "checkpoint": prepare.pin(model["checkpoint"]),
        },
        "encoder": prepare.pin(spec["campplus"]),
        "padding": {
            **padding,
            "file": prepare.pin(padded),
            "source": prepare.pin(wav001),
        },
        "conditions": {},
    }
    vectors = {}
    for name, paths in sources.items():
        for trim in ("none", "energy-vad"):
            vector, _ = reference_embedding(encoder, paths, trim=trim != "none")
            vectors[f"{name}-trim-{trim}"] = (vector, paths, [wav001])
        audio, rate = sf.read(paths[0], dtype="float32", always_2d=True)
        _, info = trim_reference_audio(audio.mean(axis=1), rate)
        record.setdefault("trim_info", {})[name] = {
            **info,
            "input_seconds": len(audio) / rate,
        }
    embedding_average, _ = reference_embedding(encoder, multi)
    baseline_multi = np.load(references["variants"]["multi-whole"]["embedding"]["path"])
    if not np.allclose(embedding_average, baseline_multi, atol=1e-6):
        raise ValueError(
            "embedding-side average does not reproduce baseline multi-whole"
        )
    individual = np.stack([reference_embedding(encoder, [p])[0] for p in multi])
    np.save(target / "b-multi-individual.npy", individual, allow_pickle=False)
    record["g_average_inputs"] = prepare.pin(target / "b-multi-individual.npy")
    for average in ("embedding", "g"):
        # g-side uses the same nominal manifest embedding; generation overrides
        # the projection with mean_i spk_proj(e_i) and verifies the nominal input.
        vectors[f"b-multi-{average}-average"] = (
            embedding_average,
            multi,
            [wav001, wav002],
        )
    for name, backends in conditions():
        vector, paths, source_utts = vectors[name]
        npy = target / f"{name}.npy"
        np.save(npy, vector, allow_pickle=False)
        jsonl = target / f"{name}.jsonl"
        jsonl.write_text(
            "".join(
                json.dumps(
                    {
                        **row,
                        "speaker_embedding_path": str(npy.resolve()),
                        "reference_audio_paths": [str(p.resolve()) for p in paths],
                    },
                    ensure_ascii=False,
                )
                + "\n"
                for row in texts
            ),
            encoding="utf-8",
        )
        manifest = root / "manifests" / f"{name}.json"
        models = {
            "torch-raw": Path(model["checkpoint"]),
            "torch-ema": Path(model["checkpoint"]),
        }
        if "onnx" in backends:
            models["onnx"] = Path(onnx_receipt["onnx"]["path"])
        created = create_manifest(
            source_path=jsonl,
            output_path=manifest,
            models=models,
            sample_rate=22050,
            asr_revision=spec["asr_revision"],
            source_revision=revision,
            asr_device="cpu",
            training_epoch=model["epoch"],
            scales=spec["scales"],
            seed=spec["seed"],
        )
        record["conditions"][name] = {
            "backends": list(backends),
            "embedding": prepare.pin(npy),
            "references": [prepare.pin(p) for p in paths],
            "source_utterances": [prepare.pin(p) for p in source_utts],
            "evaluation_input": prepare.pin(jsonl),
            "manifest": prepare.pin(manifest),
            "conditions_sha256": created["conditions_sha256"],
        }
    names = list(vectors)
    record["embedding_cosine"] = {
        a: {b: float(vectors[a][0] @ vectors[b][0]) for b in names} for a in names
    }
    prepare.write_json(root / "references.json", record)
    print("S0_PREPARE_COMPLETE", flush=True)


def _g_average_loader(original, individual, nominal):
    import torch  # noqa: PLC0415

    from piper_train.tools.cpu_reference_comparison import (  # noqa: PLC0415
        projected_average,
    )

    def load(path, *, device="auto"):
        generator, checkpoint, rate = original(path, device=device)

        def condition(speaker_embeddings=None):
            if speaker_embeddings is None:
                return None
            expected = torch.from_numpy(nominal)[None, :].to(speaker_embeddings)
            if not torch.equal(speaker_embeddings, expected):
                raise ValueError("unexpected speaker embedding for g-side average")
            # Current spk_proj weights: EMA is applied in place after loading.
            return projected_average(generator, individual).unsqueeze(-1)

        generator._get_speaker_condition = condition
        return generator, checkpoint, rate

    return load


def stage_generate(root):
    import torch  # noqa: PLC0415

    from piper_train.tools import generate_eval_audio  # noqa: PLC0415

    torch.set_num_threads(1)
    prepare = _prepare_module()
    record = _load_json(root / "references.json")
    original_loader = generate_eval_audio.load_torch_generator
    for name, backends in conditions():
        condition = record["conditions"][name]
        prepare.verify_pin(condition["manifest"])
        for backend in backends:
            directory = root / "audio" / name / backend
            if (directory / "generation.json").exists():
                continue
            print(f"S0_GENERATE {name} {backend}", flush=True)
            if name.startswith("b-multi-g-"):
                individual = np.load(record["g_average_inputs"]["path"])
                nominal = np.load(condition["embedding"]["path"])
                generate_eval_audio.load_torch_generator = _g_average_loader(
                    original_loader, individual, nominal
                )
            try:
                generate_eval_audio.generate_audio(
                    Path(condition["manifest"]["path"]),
                    backend,
                    directory,
                    device="cpu",
                )
            finally:
                generate_eval_audio.load_torch_generator = original_loader
            if name.startswith("b-multi-g-"):
                prepare.write_json(
                    root / "audio" / name / f"{backend}-override.json",
                    {
                        "override": "SynthesizerTrn._get_speaker_condition -> mean_i spk_proj(e_i)",
                        "individual_embeddings": record["g_average_inputs"],
                        "nominal_manifest_embedding": condition["embedding"],
                        "generation_sha256": prepare.pin(directory / "generation.json")[
                            "sha256"
                        ],
                    },
                )
            gc.collect()
    print("S0_GENERATE_COMPLETE", flush=True)


def stage_evaluate(root):
    from piper_train.embedding_cache import file_sha256  # noqa: PLC0415
    from piper_train.evaluation_manifest import load_manifest  # noqa: PLC0415
    from piper_train.tools.cpu_reference_comparison import (  # noqa: PLC0415
        independent_reals,
        load_native_ecapa,
        native_ecapa_embedding,
        reference_embedding,
    )
    from piper_train.tools.eval_cer import _evaluate_strict  # noqa: PLC0415
    from piper_train.tools.eval_zs_secs import (  # noqa: PLC0415
        compute_acoustics_blocks,
        compute_secs_report,
    )

    prepare = _prepare_module()
    spec, references, _, _ = _baseline()
    record = _load_json(root / "references.json")
    encoder = prepare.session(spec["campplus"])
    native = load_native_ecapa(spec["ecapa_directory"])
    ecapa_source = Path(spec["ecapa_directory"])
    native_pins = [
        prepare.pin(ecapa_source / name)
        for name in ("hyperparams.yaml", "embedding_model.ckpt")
    ]
    cache = {}

    def embeddings(paths, name):
        rows = []
        for path in paths:
            key = (file_sha256(path), name)
            if key not in cache:
                cache[key] = (
                    reference_embedding(encoder, [path])[0]
                    if name == "campplus"
                    else native_ecapa_embedding(native, path)
                )
            rows.append(cache[key])
        return np.stack(rows)

    reals = [Path(p["path"]) for p in references["cross_reals"]]
    floors = [Path(references["floor"]["path"])]
    for name, backends in conditions():
        condition = record["conditions"][name]
        manifest_path = Path(condition["manifest"]["path"])
        manifest = load_manifest(manifest_path)
        for backend in backends:
            directory = root / "audio" / name / backend
            result_path = directory / "metrics.json"
            if result_path.exists():
                continue
            print(f"S0_EVALUATE {name} {backend}", flush=True)
            cer, exit_code = _evaluate_strict(
                prepare.cer_arguments(manifest_path, directory)
            )
            prepare.write_json(directory / "cer.json", {**cer, "exit_code": exit_code})
            if exit_code == 2 or cer.get("failed_clips"):
                raise ValueError(f"strict CER execution failed: {cer}")
            synth = [directory / (clip["id"] + ".wav") for clip in manifest["clips"]]
            conditioning = [Path(p["path"]) for p in condition["references"]]
            source_utts = [Path(p["path"]) for p in condition["source_utterances"]]
            if independent_reals(reals, conditioning + source_utts) != reals:
                raise ValueError(
                    "conditioning utterance leaked into real evaluation set"
                )
            scores = {}
            for encoder_name in ("campplus", "ecapa-native"):
                ref = embeddings(conditioning, encoder_name).mean(axis=0)
                ref /= np.linalg.norm(ref)
                scores[encoder_name] = compute_secs_report(
                    embeddings(synth, encoder_name),
                    embeddings(reals, encoder_name),
                    ref_emb=ref,
                    floor_embs=embeddings(floors, encoder_name),
                )
            band, comb, prosody, comb_hnr = compute_acoustics_blocks(synth, reals)
            prepare.write_json(
                result_path,
                {
                    "model": MODEL_ID,
                    "variant": name,
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
                    "pinned_inputs": [
                        prepare.pin(p)
                        for p in synth + reals + floors + conditioning + source_utts
                    ]
                    + [prepare.pin(spec["campplus"])]
                    + native_pins,
                    "evaluation_frontend": "unchanged baseline: CAM++ whole no-trim; native ECAPA waveform",
                    "scope": "Japanese single-speaker diagnostic; not human quality acceptance",
                },
            )
            gc.collect()
    print("S0_EVALUATE_COMPLETE", flush=True)


def _separability_set():
    """(path, speaker, corpus) for every locally available real speaker."""
    spec = _load_json(BASELINE / "experiment.json")
    from piper_train.embedding_cache import file_sha256  # noqa: PLC0415

    rows = []
    tsukuyomi = sorted(Path(spec["reference_sources"][0]).parent.glob("*.wav"))
    rows += [(p, "tsukuyomi", "tsukuyomi-raw") for p in tsukuyomi]
    singles = sorted(
        (ROOT.parent / "piper-v8-dataset-backup").glob(
            "*_listen_samples/*/reference_original.wav"
        )
    )
    seen = set()
    for path in singles:
        # tsukuyomi_* listen references are the tsukuyomi speaker (not a new
        # speaker label) and may be derived copies of tsukuyomi-raw utterances.
        if path.parent.name.startswith("tsukuyomi"):
            continue
        digest = file_sha256(path)
        if digest not in seen:
            seen.add(digest)
            rows.append((path, path.parent.name, "v8-listen-reference"))
    metadata = MOE_SPEECH / "metadata.csv"
    if metadata.is_file():
        by_speaker = {}
        for line in metadata.read_text(encoding="utf-8").splitlines():
            utterance, speaker = line.split("|")[:2]
            by_speaker.setdefault(speaker, []).append(utterance)
        for speaker, utterances in sorted(by_speaker.items()):
            utterances.sort()
            picks = np.linspace(0, len(utterances) - 1, PER_SPEAKER).round().astype(int)
            for index in picks:
                path = MOE_SPEECH / "wavs_extracted/wavs" / f"{utterances[index]}.wav"
                rows.append((path, f"moe-{speaker}", "moe-speech-20speakers"))
    return rows


def stage_separability(root):
    import torch  # noqa: PLC0415

    from piper_train.extract_speaker_embedding import (  # noqa: PLC0415
        _load_campplus_stats_model,
        extract_embedding,
        preprocess_audio,
    )
    from piper_train.reference_frontend import campplus_stats  # noqa: PLC0415
    from piper_train.tools.cpu_reference_comparison import (  # noqa: PLC0415
        pairwise_separability,
    )

    torch.set_num_threads(4)
    prepare = _prepare_module()
    spec = _load_json(BASELINE / "experiment.json")
    encoder = prepare.session(spec["campplus"])
    model = _load_campplus_stats_model(TORCH_CAMPPLUS)
    rows = _separability_set()
    features = {}
    for trim in (False, True):
        emb, stats = [], []
        for path, _, _ in rows:
            fbank = preprocess_audio(path, trim=trim)
            emb.append(extract_embedding(encoder, fbank))
            with torch.inference_mode():
                stats.append(
                    campplus_stats(model, torch.from_numpy(fbank)[None])[0].numpy()
                )
        features[trim] = (np.stack(emb), np.stack(stats))
    tsukuyomi_idx = [i for i, r in enumerate(rows) if r[1] == "tsukuyomi"]
    capped_tsukuyomi = set(
        np.asarray(tsukuyomi_idx)[
            np.linspace(0, len(tsukuyomi_idx) - 1, PER_SPEAKER).round().astype(int)
        ].tolist()
    )
    subsets = {
        # Controller ruling R1 scope: tsukuyomi + baseline floor candidates + other
        # single-reference speakers under the local backup (all tsukuyomi utts).
        "r1-local-output": [
            i for i, r in enumerate(rows) if r[2] != "moe-speech-20speakers"
        ],
        # Extended: adds 20 MOE-Speech speakers already in the local HF cache
        # (no download); tsukuyomi capped to the same per-speaker count.
        "extended-capped": [
            i
            for i, r in enumerate(rows)
            if r[1] != "tsukuyomi" or i in capped_tsukuyomi
        ],
    }
    result = {
        "version": 1,
        "encoder_onnx": prepare.pin(spec["campplus"]),
        "encoder_torch": prepare.pin(TORCH_CAMPPLUS),
        "moe_speech_snapshot": str(MOE_SPEECH),
        "frontend": "preprocess_audio (soxr HQ 16k, kaldi fbank80, CMN); whole utterance",
        "stats": "campplus_stats: fp32 mean + unbiased std of out_nonlinear (1024-d)",
        "utterances": [{"path": str(p), "speaker": s, "corpus": c} for p, s, c in rows],
        "subsets": {},
    }
    for subset, indices in subsets.items():
        labels = [rows[i][1] for i in indices]
        block = {}
        for trim, (emb, stats) in features.items():
            key = "trim=energy-vad" if trim else "trim=none"
            block[key] = {
                "campplus192_raw": pairwise_separability(emb[indices], labels),
                "campplus192_standardized": pairwise_separability(
                    emb[indices], labels, standardize=True
                ),
                "stats1024_raw": pairwise_separability(stats[indices], labels),
                "stats1024_standardized": pairwise_separability(
                    stats[indices], labels, standardize=True
                ),
            }
            block[key]["decision"] = stats_decision(
                block[key]["stats1024_standardized"], block[key]["campplus192_raw"]
            )
        result["subsets"][subset] = block
    prepare.write_json(root / "separability.json", result)
    print(
        json.dumps(
            {
                s: {
                    k: {f: round(v[f]["auc"], 4) for f in v if f != "decision"}
                    for k, v in b.items()
                }
                for s, b in result["subsets"].items()
            },
            indent=1,
        )
    )
    print("S0_SEPARABILITY_COMPLETE", flush=True)


def _cell(groups, name, base, backend):
    group, reference = groups[(name, backend)], groups[(base, backend)]
    enc, ref = group["encoders"], reference["encoders"]
    return {
        "cell": f"{name} vs {base} / {backend}",
        "campplus_delta": enc["campplus"]["cross_utt_secs"]
        - ref["campplus"]["cross_utt_secs"],
        "ecapa_delta": enc["ecapa-native"]["cross_utt_secs"]
        - ref["ecapa-native"]["cross_utt_secs"],
        "cer_delta": group["cer"]["cer_median"] - reference["cer"]["cer_median"],
        "flags": {
            f"{e}_above_ceiling": bool(enc[e]["cross_exceeds_ceiling"])
            for e in ("campplus", "ecapa-native")
        },
    }


def stage_summary(root):
    from piper_train.tools.eval_zs_secs import compare_with_baseline  # noqa: PLC0415

    prepare = _prepare_module()
    groups = {}
    for name, backends in conditions():
        for backend in backends:
            groups[(name, backend)] = _load_json(
                root / "audio" / name / backend / "metrics.json"
            )
    trim_cells, average_cells, comparisons = [], [], []
    for base_name in TRIM_CONDITIONS:
        for backend in ALL_BACKENDS:
            name, base = f"{base_name}-trim-energy-vad", f"{base_name}-trim-none"
            cell = _cell(groups, name, base, backend)
            speaker = compare_with_baseline(
                groups[(name, backend)],
                groups[(base, backend)],
                secondary="ecapa-native",
            )
            cell["flags"]["goodhart"] = bool(speaker.get("goodhart_flag"))
            trim_cells.append(cell)
            comparisons.append({"cell": cell["cell"], "speaker": speaker})
    for backend in AVERAGE_BACKENDS:
        name, base = "b-multi-g-average", "b-multi-embedding-average"
        cell = _cell(groups, name, base, backend)
        speaker = compare_with_baseline(
            groups[(name, backend)], groups[(base, backend)], secondary="ecapa-native"
        )
        cell["flags"]["goodhart"] = bool(speaker.get("goodhart_flag"))
        average_cells.append(cell)
        comparisons.append({"cell": cell["cell"], "speaker": speaker})
    separability = _load_json(root / "separability.json")
    trim = trim_decision(trim_cells)
    frontend = "kaldi-fbank80-cmn@16k;trim=" + (
        "energy-vad" if trim["adopt_trim"] else "none"
    )
    trim_key = "trim=energy-vad" if trim["adopt_trim"] else "trim=none"
    table = [
        {
            "condition": name,
            "backend": backend,
            "cer_median": g["cer"]["cer_median"],
            "campplus_cross": g["encoders"]["campplus"]["cross_utt_secs"],
            "ecapa_cross": g["encoders"]["ecapa-native"]["cross_utt_secs"],
            "campplus_same": g["encoders"]["campplus"]["same_utt_secs"],
            "ecapa_same": g["encoders"]["ecapa-native"]["same_utt_secs"],
            "campplus_transfer": g["encoders"]["campplus"]["normalized_transfer"],
            "ecapa_transfer": g["encoders"]["ecapa-native"]["normalized_transfer"],
        }
        for (name, backend), g in groups.items()
    ]
    summary = {
        "version": 1,
        "references": prepare.pin(root / "references.json"),
        "separability": prepare.pin(root / "separability.json"),
        "groups": table,
        "trim_cells": trim_cells,
        "average_cells": average_cells,
        "comparisons": comparisons,
        "g0": {
            "trim": trim,
            "averaging": averaging_decision(average_cells),
            "stats": {
                subset: block[trim_key]["decision"]
                for subset, block in separability["subsets"].items()
            },
            "frontend": frontend,
        },
    }
    prepare.write_json(root / "summary.json", summary)
    print(json.dumps(summary["g0"], ensure_ascii=False, indent=1))
    for row in table:
        print(row)
    print("S0_SUMMARY_COMPLETE", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("prepare", "generate", "evaluate", "separability", "summary"),
    )
    args = parser.parse_args(argv)
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    root = args.output.resolve()
    if BASELINE.resolve() in (root, *root.parents):
        raise ValueError("S0 outputs must not be written under the baseline directory")
    root.mkdir(parents=True, exist_ok=True)
    {
        "prepare": stage_prepare,
        "generate": stage_generate,
        "evaluate": stage_evaluate,
        "separability": stage_separability,
        "summary": stage_summary,
    }[args.stage](root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
