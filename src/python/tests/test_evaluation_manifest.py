"""Pinned evaluation inputs; fixture hashes do not assert model quality."""

import json
from pathlib import Path

import numpy as np
import pytest


pytestmark = pytest.mark.unit


@pytest.fixture
def evaluation_inputs(tmp_path):
    for name in ("model.ckpt", "model.onnx", "reference.wav"):
        (tmp_path / name).write_bytes(name.encode())
    np.save(tmp_path / "reference.npy", np.arange(1, 193, dtype=np.float32))
    rows = [
        {
            "id": f"t{i}",
            "text": text,
            "phoneme_ids": [1, 10, 2],
            "language_id": 0,
            "speaker_embedding_path": "reference.npy",
            "reference_audio_paths": ["reference.wav"],
        }
        for i, text in enumerate(["こんにちは", "ありがとう", "さようなら"])
    ]
    source = tmp_path / "test.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    options = {
        "source_path": source,
        "output_path": tmp_path / "manifest.json",
        "models": {
            "torch-raw": tmp_path / "model.ckpt",
            "torch-ema": tmp_path / "model.ckpt",
            "onnx": tmp_path / "model.onnx",
        },
        "sample_rate": 22050,
        "asr_revision": "a" * 40,
        "source_revision": "b" * 40,
    }
    return source, rows, options


def test_manifest_pins_source_reference_models_and_recipe(evaluation_inputs):
    from piper_train.embedding_cache import file_sha256
    from piper_train.evaluation_manifest import create_manifest, load_manifest

    source, rows, options = evaluation_inputs
    create_manifest(**options)
    manifest = load_manifest(options["output_path"])
    assert [clip["id"] for clip in manifest["clips"]] == [row["id"] for row in rows]
    assert manifest["source"]["input_sha256"] == file_sha256(source)
    assert manifest["source"]["revision"] == "b" * 40
    assert manifest["asr"]["revision"] == "a" * 40
    assert manifest["asr"]["normalization"] == "nfkc-strip-PZS-v1"
    assert manifest["scales"] == [0.4, 1.0, 0.5]
    assert manifest["seed"] == 42
    for clip in manifest["clips"]:
        assert clip["speaker_embedding_sha256"] == file_sha256(
            Path(clip["speaker_embedding_path"])
        )
        assert clip["reference_audio"][0]["sha256"]
        assert clip["text_sha256"]
    assert set(manifest["models"]) == {"torch-raw", "torch-ema", "onnx"}


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "unsafe-id",
        "empty-text",
        "missing-reference",
        "invalid-vector",
        "missing-ids",
        "no-reference",
    ],
)
def test_manifest_rejects_ambiguous_or_invalid_inputs(evaluation_inputs, mutation):
    from piper_train.evaluation_manifest import create_manifest

    source, rows, options = evaluation_inputs
    if mutation == "duplicate":
        rows[1]["id"] = rows[0]["id"]
    elif mutation == "unsafe-id":
        rows[0]["id"] = "../escape"
    elif mutation == "empty-text":
        rows[0]["text"] = ""
    elif mutation == "missing-reference":
        rows[0]["speaker_embedding_path"] = "missing.npy"
    elif mutation == "invalid-vector":
        np.save(source.parent / "reference.npy", np.full(192, np.nan))
    elif mutation == "missing-ids":
        rows[0].pop("phoneme_ids")
    else:
        rows[0].pop("speaker_embedding_path")
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(ValueError):
        create_manifest(**options)
    assert not options["output_path"].exists()


@pytest.mark.parametrize("target", ["reference.npy", "reference.wav", "model.onnx"])
def test_loading_manifest_detects_changed_pinned_files(evaluation_inputs, target):
    from piper_train.evaluation_manifest import create_manifest, load_manifest

    source, _rows, options = evaluation_inputs
    create_manifest(**options)
    (source.parent / target).write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        load_manifest(options["output_path"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("training_epoch", -1),
        ("training_epoch", True),
        ("source_revision", "dev"),
        ("seed", 2**63 - 1),
    ],
)
def test_manifest_rejects_unpinned_epoch_revision_or_overflowing_clip_seed(
    evaluation_inputs, field, value
):
    from piper_train.evaluation_manifest import create_manifest

    _source, _rows, options = evaluation_inputs
    options[field] = value
    with pytest.raises(ValueError):
        create_manifest(**options)
    assert not options["output_path"].exists()


def test_manifest_pins_actual_source_files_and_detects_changes(
    evaluation_inputs, monkeypatch
):
    from piper_train import evaluation_manifest as manifests
    from piper_train.embedding_cache import file_sha256

    source, _rows, options = evaluation_inputs
    implementation = source.parent / "implementation.py"
    implementation.write_text("version = 1\n", encoding="utf-8")
    monkeypatch.setattr(manifests, "_source_files", lambda: [implementation])
    manifest = manifests.create_manifest(**options)
    assert manifest["source"]["files"] == [
        {"path": str(implementation), "sha256": file_sha256(implementation)}
    ]
    implementation.write_text("version = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        manifests.load_manifest(options["output_path"])


def test_inline_reference_has_priority_and_is_pinned(evaluation_inputs):
    from piper_train.evaluation_manifest import create_manifest, validate_manifest

    source, rows, options = evaluation_inputs
    rows[0]["speaker_embedding"] = [1.0] * 192
    rows[0]["speaker_embedding_path"] = "unused-missing.npy"
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    manifest = create_manifest(**options)
    assert manifest["clips"][0]["speaker_embedding_path"] is None
    vector = manifest["clips"][0]["speaker_embedding"]
    assert np.linalg.norm(vector) == pytest.approx(1)
    manifest["clips"][0]["speaker_embedding"][0] += 0.1
    with pytest.raises(ValueError, match="hash"):
        validate_manifest(manifest)


def test_raw_ema_and_onnx_generation_share_conditions_and_emit_raw_wav(
    evaluation_inputs, monkeypatch
):
    torch = pytest.importorskip(
        "torch", reason="Torch backend generation requires torch"
    )

    from piper_train.evaluation_manifest import create_manifest
    from piper_train.tools import generate_eval_audio as generation
    from piper_train.vits.wavfile import read

    source, _rows, options = evaluation_inputs
    create_manifest(**options)

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.dec = torch.nn.Linear(1, 1, bias=False)
            self.spk_proj = torch.nn.Identity()
            self.dec.weight.data.fill_(0.25)
            self.calls = []

        def infer(self, text, lengths, **kwargs):
            self.calls.append(
                {
                    "text": text.tolist(),
                    "lengths": lengths.tolist(),
                    "training": self.training,
                    "grad": torch.is_grad_enabled(),
                    **kwargs,
                }
            )
            return (self.dec.weight.reshape(1, 1, 1).expand(1, 1, 32),)

    raw_generator = Tiny()
    checkpoint = {
        "ema_generator_state": {"shadow_params": {"weight": torch.full((1, 1), 0.5)}}
    }
    monkeypatch.setattr(
        generation,
        "load_torch_generator",
        lambda path: (raw_generator, checkpoint, 22050),
    )
    feeds = []

    class Session:
        def get_outputs(self):
            from types import SimpleNamespace

            return [SimpleNamespace(name="durations"), SimpleNamespace(name="output")]

        def get_inputs(self):
            from types import SimpleNamespace

            return [
                SimpleNamespace(
                    name=name, shape=[1, 192] if name == "speaker_embedding" else []
                )
                for name in [
                    "input",
                    "input_lengths",
                    "scales",
                    "speaker_embedding",
                    "speaker_embedding_mask",
                    "lid",
                ]
            ]

        def run(self, outputs, values):
            assert outputs == ["output"]
            feeds.append(values)
            return [np.full((1, 1, 32), 0.25, dtype=np.float32)]

    seeds = []

    def session_factory(path, seed):
        seeds.append(seed)
        return Session()

    monkeypatch.setattr(generation, "load_onnx_session", session_factory)
    reports = {}
    for backend in ["torch-raw", "torch-ema", "onnx"]:
        output = source.parent / backend
        reports[backend] = generation.generate_audio(
            options["output_path"], backend, output
        )
        sample_rate, values = read(output / "t0.wav")
        assert sample_rate == 22050 and values.dtype == np.float32
        np.testing.assert_array_equal(
            values,
            np.full(32, 0.5 if backend == "torch-ema" else 0.25, dtype=np.float32),
        )
        assert reports[backend]["clips"][0]["wav_sha256"]
        assert (output / "generation.json").is_file()
    assert len({report["conditions_sha256"] for report in reports.values()}) == 1
    assert seeds == [42, 43, 44]
    assert len(raw_generator.calls) == len(feeds) * 2 == 6
    assert raw_generator.training and raw_generator.dec.weight.item() == pytest.approx(
        0.25
    )
    for call in raw_generator.calls:
        assert not call["training"] and not call["grad"]
        assert call["speaker_embeddings"].norm().item() == pytest.approx(1)
        assert "f0" not in call and "duration" not in call
    for feed in feeds:
        assert feed["speaker_embedding_mask"].tolist() == [[1]]
        assert np.linalg.norm(feed["speaker_embedding"]) == pytest.approx(1)


def test_ema_generation_refuses_to_label_raw_weights_as_ema(
    evaluation_inputs, monkeypatch
):
    torch = pytest.importorskip("torch", reason="EMA backend generation requires torch")

    from piper_train.evaluation_manifest import create_manifest
    from piper_train.tools import generate_eval_audio as generation

    source, _rows, options = evaluation_inputs
    create_manifest(**options)
    model = torch.nn.Linear(1, 1)
    model.spk_proj = torch.nn.Identity()
    monkeypatch.setattr(
        generation,
        "load_torch_generator",
        lambda path: (model, {}, 22050),
    )
    with pytest.raises(ValueError, match="EMA"):
        generation.generate_audio(
            options["output_path"], "torch-ema", source.parent / "output"
        )
    assert not (source.parent / "output/generation.json").exists()


@pytest.mark.parametrize("failure", ["epoch-mismatch", "unsupported-reference"])
def test_generation_rejects_checkpoint_condition_mismatch(
    evaluation_inputs, monkeypatch, failure
):
    torch = pytest.importorskip("torch", reason="checkpoint condition fixture")
    from piper_train.evaluation_manifest import create_manifest
    from piper_train.tools import generate_eval_audio as generation

    source, _rows, options = evaluation_inputs
    create_manifest(**options, training_epoch=40)
    model = torch.nn.Linear(1, 1)
    if failure == "epoch-mismatch":
        model.spk_proj = torch.nn.Identity()
    monkeypatch.setattr(
        generation,
        "load_torch_generator",
        lambda path: (
            model,
            {"epoch": 39 if failure == "epoch-mismatch" else 40},
            22050,
        ),
    )
    with pytest.raises(ValueError, match=r"epoch|speaker_embedding"):
        generation.generate_audio(
            options["output_path"], "torch-raw", source.parent / "bad-audio"
        )
    assert not (source.parent / "bad-audio/generation.json").exists()


def test_failed_ema_generation_restores_weights_modes_and_rng(
    evaluation_inputs, monkeypatch
):
    torch = pytest.importorskip("torch", reason="EMA rollback fixture")
    import copy
    import random

    from piper_train.evaluation_manifest import create_manifest
    from piper_train.tools import generate_eval_audio as generation

    class Failing(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.dec = torch.nn.Linear(1, 1, bias=False)
            self.spk_proj = torch.nn.Identity()
            self.calls = 0

        def infer(self, *args, **kwargs):
            self.calls += 1
            torch.rand(1)
            np.random.rand()
            random.random()
            if self.calls == 2:
                raise RuntimeError("fixture generation failure")
            return (torch.ones(1, 1, 32),)

    source, _rows, options = evaluation_inputs
    create_manifest(**options)
    model = Failing()
    model.dec.eval()
    weights = copy.deepcopy(model.state_dict())
    rng, numpy_rng, python_rng = (
        torch.random.get_rng_state().clone(),
        np.random.get_state(),
        random.getstate(),
    )
    checkpoint = {
        "ema_generator_state": {"shadow_params": {"weight": torch.ones(1, 1)}}
    }
    monkeypatch.setattr(
        generation, "load_torch_generator", lambda path: (model, checkpoint, 22050)
    )
    with pytest.raises(RuntimeError, match="fixture generation failure"):
        generation.generate_audio(
            options["output_path"], "torch-ema", source.parent / "partial"
        )
    assert not (source.parent / "partial/generation.json").exists()
    for name, value in model.state_dict().items():
        assert torch.equal(value, weights[name])
    assert model.training and not model.dec.training
    assert torch.equal(rng, torch.random.get_rng_state())
    np.testing.assert_array_equal(numpy_rng[1], np.random.get_state()[1])
    assert (
        numpy_rng[2:] == np.random.get_state()[2:] and python_rng == random.getstate()
    )


@pytest.mark.parametrize("compiled", [False, True])
def test_real_torch_checkpoint_loader_preserves_rng_and_generates_audio(
    evaluation_inputs, monkeypatch, compiled
):
    torch = pytest.importorskip("torch", reason="real Torch inference fixture")
    pytest.importorskip("pytorch_lightning", reason="real checkpoint loading fixture")
    import copy
    import sys
    from types import SimpleNamespace

    from piper_train import extract_speaker_embedding as extraction
    from piper_train.tools import generate_eval_audio as generation
    from piper_train.vits import lightning
    from piper_train.vits.dataset import PiperDataset
    from piper_train.vits.wavfile import read

    source, rows, options = evaluation_inputs
    monkeypatch.setattr(
        lightning, "MultiPeriodDiscriminator", lambda **kwargs: torch.nn.Linear(1, 1)
    )
    model = lightning.VitsModel(
        num_symbols=50,
        num_speakers=2,
        dataset=None,
        use_wavlm_discriminator=False,
        inter_channels=8,
        hidden_channels=8,
        filter_channels=16,
        n_heads=2,
        n_layers=1,
        n_layers_q=1,
        gin_channels=16,
        prosody_dim=0,
        use_sdp=False,
        upsample_initial_channel=32,
        upsample_rates=(2, 2),
        upsample_kernel_sizes=(4, 4),
        resblock_kernel_sizes=(3,),
        resblock_dilation_sizes=((1, 2),),
    )
    checkpoint_path = source.parent / "model.ckpt"
    torch.save(
        {
            "hyper_parameters": dict(model.hparams),
            "state_dict": {
                name.replace("model_g.dec.", "model_g.dec._orig_mod.")
                if compiled
                else name: value
                for name, value in model.state_dict().items()
            },
            "epoch": 40,
            "ema_generator_state": {
                "shadow_params": {
                    name: parameter.detach().clone() + 0.001
                    for name, parameter in model.model_g.dec.named_parameters()
                }
            },
            "ema_spk_proj_state": {
                "shadow_params": {
                    name: parameter.detach().clone()
                    for name, parameter in model.model_g.spk_proj.named_parameters()
                }
            },
        },
        checkpoint_path,
    )
    before = torch.random.get_rng_state().clone()
    loaded, _checkpoint, rate = generation.load_torch_generator(checkpoint_path)
    assert torch.equal(before, torch.random.get_rng_state())
    assert rate == 22050
    for name, value in model.model_g.state_dict().items():
        assert torch.equal(value, loaded.state_dict()[name]), name
    for row in rows:
        row["phoneme_ids"] = [1] + [10] * 16 + [2]
        row["audio_norm_path"] = "audio.pt"
        row["audio_spec_path"] = "spec.pt"
    torch.save(torch.zeros(1, 4096), source.parent / "audio.pt")
    torch.save(torch.zeros(513, 20), source.parent / "spec.pt")
    dataset_path = source.parent / "dataset.jsonl"
    dataset_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    class Encoder:
        def __init__(self):
            self._model_path = str(source.parent / "encoder.onnx")
            Path(self._model_path).write_bytes(b"encoder fixture")

        def get_inputs(self):
            return [SimpleNamespace(name="features")]

        def get_outputs(self):
            return [SimpleNamespace(name="embedding")]

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, outputs, feeds):
            count = next(iter(feeds.values())).shape[0]
            return [np.tile(np.arange(1, 193, dtype=np.float32), (count, 1))]

    def frontend(self, index):
        entry, _path, key = self.items[index]
        return entry, torch.ones(2, self.fixed_frames, 80), key, True

    monkeypatch.setattr(extraction._FbankDataset, "__getitem__", frontend)
    extraction.extract_per_utterance(
        Encoder(),
        dataset_dir=source.parent,
        output_dir=source.parent / "extracted",
        num_workers=0,
    )
    rows = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
    ]
    loaded_dataset = PiperDataset([dataset_path])
    reference = loaded_dataset[0].speaker_embedding
    assert reference.norm().item() == pytest.approx(1)
    fixed = model._load_test_dataset(dataset_path)[0]
    torch.testing.assert_close(fixed.speaker_embedding, reference)
    model._test_dataset = model._load_test_dataset(dataset_path)
    model.hparams.dataset_dir = source.parent
    model.hparams.audio_log_epochs = 1
    model._trainer = SimpleNamespace(
        is_global_zero=True, world_size=1, current_epoch=0, global_step=1
    )
    from unittest.mock import MagicMock

    model.optimizers = MagicMock(
        side_effect=AssertionError("monitor must not access optimizers")
    )
    logger = SimpleNamespace(experiment=MagicMock())
    monkeypatch.setattr(model, "_get_wandb_logger", lambda: logger)
    monkeypatch.setattr(lightning, "WANDB_AVAILABLE", True)
    monkeypatch.setattr(
        lightning,
        "wandb",
        SimpleNamespace(Audio=MagicMock(), Table=lambda **kwargs: kwargs),
    )
    monitor_state = copy.deepcopy(model.state_dict())
    monitor_clock = (
        model.training_batches_seen,
        model.generator_updates,
        model.discriminator_updates,
        model._kl_cap_consecutive,
    )
    monitor_rng = torch.random.get_rng_state().clone()
    model.on_validation_epoch_end()
    assert logger.experiment.log.called
    model.optimizers.assert_not_called()
    assert torch.equal(monitor_rng, torch.random.get_rng_state())
    assert monitor_clock == (
        model.training_batches_seen,
        model.generator_updates,
        model.discriminator_updates,
        model._kl_cap_consecutive,
    )
    for name, value in model.state_dict().items():
        assert torch.equal(value, monitor_state[name]), name
    pytest.importorskip("onnx", reason="common manifest exported ONNX backend")
    pytest.importorskip("onnxruntime", reason="common manifest exported ONNX backend")
    from piper_train.export_onnx import build_infer_forward, set_export_mode

    # Export the same real fixture through the existing infer wrapper, without
    # introducing a second implementation of inference into the evaluator.
    exported = model.model_g
    exported.eval()
    set_export_mode(exported, True)
    exported.dec.remove_weight_norm()
    exported.forward = build_infer_forward(exported, stochastic=True)
    onnx_path = source.parent / "model.onnx"
    with torch.no_grad():
        torch.onnx.export(
            exported,
            (
                torch.tensor([rows[0]["phoneme_ids"]]),
                torch.tensor([len(rows[0]["phoneme_ids"])]),
                torch.tensor([0.4, 1.0, 0.5]),
                reference.unsqueeze(0),
            ),
            str(onnx_path),
            opset_version=15,
            dynamo=False,
            input_names=["input", "input_lengths", "scales", "speaker_embedding"],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {1: "phonemes"},
                "output": {2: "samples"},
                "durations": {1: "phonemes"},
            },
        )
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generation",
            "prepare",
            "--test-jsonl",
            str(source),
            "--output",
            str(options["output_path"]),
            "--checkpoint",
            str(checkpoint_path),
            "--onnx",
            str(onnx_path),
            "--asr-revision",
            "a" * 40,
            "--epoch",
            "40",
        ],
    )
    assert generation.main() == 0
    weights = copy.deepcopy(loaded.state_dict())
    # Offline extraction owns a DataLoader RNG; the inference context restores
    # the state at entry, independently of earlier dataset preparation.
    before = torch.random.get_rng_state().clone()
    monkeypatch.setattr(
        generation, "load_torch_generator", lambda path: (loaded, _checkpoint, rate)
    )
    output = source.parent / "real-audio"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generation",
            "generate",
            "--manifest",
            str(options["output_path"]),
            "--backend",
            "torch-raw",
            "--output-dir",
            str(output),
        ],
    )
    assert generation.main() == 0
    report = json.loads((output / "generation.json").read_text(encoding="utf-8"))
    assert report["training_epoch"] == 40 and len(report["clips"]) == 3
    for clip in report["clips"]:
        _, audio = read(output / (clip["id"] + ".wav"))
        assert audio.size > 0 and np.isfinite(audio).all()
    assert torch.equal(before, torch.random.get_rng_state())
    for name, value in loaded.state_dict().items():
        assert torch.equal(value, weights[name]), name
    ema = generation.generate_audio(
        options["output_path"], "torch-ema", source.parent / "real-ema"
    )
    assert ema["conditions_sha256"] == report["conditions_sha256"]
    assert all(
        applied > 0 and skipped == 0 for applied, skipped in ema["ema_applied"].values()
    )
    assert torch.equal(before, torch.random.get_rng_state())
    for name, value in loaded.state_dict().items():
        assert torch.equal(value, weights[name]), name
    onnx_report = generation.generate_audio(
        options["output_path"], "onnx", source.parent / "real-onnx"
    )
    assert (
        onnx_report["conditions_sha256"]
        == report["conditions_sha256"]
        == ema["conditions_sha256"]
    )
    for clip in onnx_report["clips"]:
        sample_rate, audio = read(source.parent / "real-onnx" / (clip["id"] + ".wav"))
        assert sample_rate == 22050 and audio.size and np.isfinite(audio).all()
    from piper_train.tools import eval_cer

    expected = {row["id"]: row["text"] for row in rows}
    monkeypatch.setattr(
        eval_cer,
        "build_whisper_transcribe_fn",
        lambda *args, **kwargs: lambda wav: expected[wav.stem],
    )
    result_path = source.parent / "cer.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_cer",
            "--clips-dir",
            str(output),
            "--manifest",
            str(options["output_path"]),
            "--json-out",
            str(result_path),
        ],
    )
    assert eval_cer.main() == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["gate_passed"] is True


def test_real_onnx_named_audio_output_and_per_clip_seed(evaluation_inputs, monkeypatch):
    onnx = pytest.importorskip("onnx", reason="real ONNX inference fixture")
    pytest.importorskip("onnxruntime", reason="real ONNX inference fixture")
    import sys

    from piper_train.evaluation_manifest import create_manifest
    from piper_train.tools import generate_eval_audio as generation
    from piper_train.vits.wavfile import read

    source, _rows, options = evaluation_inputs
    helper, tensor = onnx.helper, onnx.TensorProto
    inputs = [
        helper.make_tensor_value_info("input", tensor.INT64, [1, "T"]),
        helper.make_tensor_value_info("input_lengths", tensor.INT64, [1]),
        helper.make_tensor_value_info("scales", tensor.FLOAT, [3]),
        helper.make_tensor_value_info("speaker_embedding", tensor.FLOAT, [1, 192]),
    ]
    graph = helper.make_graph(
        [
            helper.make_node(
                "Constant",
                [],
                ["durations"],
                value=helper.make_tensor("d", tensor.FLOAT, [1], [999]),
            ),
            helper.make_node("RandomNormal", [], ["output"], shape=[1, 1, 32]),
        ],
        "seeded-evaluation-fixture",
        inputs,
        [
            helper.make_tensor_value_info("durations", tensor.FLOAT, [1]),
            helper.make_tensor_value_info("output", tensor.FLOAT, [1, 1, 32]),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 10
    onnx.save(model, source.parent / "model.onnx")
    create_manifest(**options)
    arrays = []
    for run in range(2):
        output = source.parent / f"onnx-{run}"
        if run == 0:
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "generation",
                    "generate",
                    "--manifest",
                    str(options["output_path"]),
                    "--backend",
                    "onnx",
                    "--output-dir",
                    str(output),
                ],
            )
            assert generation.main() == 0
            report = json.loads(
                (output / "generation.json").read_text(encoding="utf-8")
            )
        else:
            report = generation.generate_audio(options["output_path"], "onnx", output)
        assert [clip["seed"] for clip in report["clips"]] == [42, 43, 44]
        values = [read(output / f"t{i}.wav")[1] for i in range(3)]
        assert all(value.size == 32 for value in values)
        arrays.append(values)
    for a, b in zip(*arrays, strict=True):
        np.testing.assert_array_equal(a, b)
    assert not np.array_equal(arrays[0][0], arrays[0][1])
