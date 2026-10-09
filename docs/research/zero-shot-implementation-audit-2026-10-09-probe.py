"""CPU reproduction of the existing manual-optimizer schedule.

Uses the real VitsModel.training_step and training_step_d with small linear
modules. Only generator waveform/loss computation is replaced. The WavLM G
gate is compiled from the existing training_step_g AST, rather than rewritten.
No pretrained model, audio synthesis, GPU training, or network is used.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import inspect
import io
import json
import struct
import sys
import tarfile
import tempfile
import textwrap
import wave
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

import numpy as np  # noqa: E402
import pytorch_lightning as pl  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402
from tensorboard.compat.proto.event_pb2 import Event  # noqa: E402
from torch import nn  # noqa: E402
from torch.utils.data import DataLoader, TensorDataset  # noqa: E402

from piper_train.extract_speaker_embedding import (  # noqa: E402
    _FbankDataset,
    extract_from_dataset,
    extract_per_utterance,
    preprocess_audio,
)
from piper_train.infer_onnx import _resolve_speaker_embedding  # noqa: E402
from piper_train.tools import eval_cer  # noqa: E402
from piper_train.vits.lightning import VitsModel  # noqa: E402
from piper_train.vits.losses import generator_loss  # noqa: E402
from piper_train.vits.models import SynthesizerTrn  # noqa: E402


class FakeSpeakerSession:
    """CPU-only ONNX stand-in for cache and manifest probes."""

    def __init__(self, value: float = 1.0):
        self.value = value
        self.calls = 0

    class _Input:
        name = "input"

    class _Output:
        name = "output"

    def get_inputs(self):
        return [self._Input()]

    def get_outputs(self):
        return [self._Output()]

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def run(self, _output_names, inputs):
        self.calls += 1
        batch = next(iter(inputs.values())).shape[0]
        row = self.value + np.arange(192, dtype=np.float32) * 0.01
        return [np.tile(row, (batch, 1))]


def _write_dataset(root: Path, rows: list[dict]) -> None:
    (root / "dataset.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_dataset(root: Path) -> list[dict]:
    return [
        json.loads(line) for line in (root / "dataset.jsonl").read_text().splitlines()
    ]


def pipeline_probes() -> dict:
    """Reproduce path/cache/input issues without GPU or real ONNX weights."""

    result = {}

    with tempfile.TemporaryDirectory(prefix="zs-probe-output-dir-") as tmp:
        root = Path(tmp)
        custom = root / "custom"
        torch.save(torch.zeros(22050), root / "utt.pt")
        _write_dataset(root, [{"audio_norm_path": "utt.pt"}])
        extract_per_utterance(
            FakeSpeakerSession(),
            root,
            output_dir=custom,
            source_sr=22050,
            batch_size=1,
            num_workers=0,
            fixed_frames=0,
        )
        result["output_dir_ignored"] = {
            "custom_exists": (custom / "utt.npy").exists(),
            "dataset_default_exists": (
                root / "speaker_embeddings" / "utt.npy"
            ).exists(),
            "evidence": "extract_speaker_embedding.py:518-519,991-995",
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-stem-") as tmp:
        root = Path(tmp)
        for sub in ("a", "b"):
            (root / sub).mkdir()
            torch.save(torch.zeros(22050), root / sub / "foo.pt")
        _write_dataset(
            root, [{"audio_norm_path": "a/foo.pt"}, {"audio_norm_path": "b/foo.pt"}]
        )
        extract_per_utterance(
            FakeSpeakerSession(),
            root,
            source_sr=22050,
            batch_size=2,
            num_workers=0,
            fixed_frames=0,
        )
        result["stem_collision"] = {
            "json_paths": [
                row["speaker_embedding_path"] for row in _read_dataset(root)
            ],
            "cache_files": sorted(
                path.name for path in (root / "speaker_embeddings").glob("*.npy")
            ),
            "evidence": "extract_speaker_embedding.py:540-551,687,762-763",
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-missing-") as tmp:
        root = Path(tmp)
        torch.save(torch.zeros(22050), root / "ok.pt")
        _write_dataset(
            root, [{"audio_norm_path": "ok.pt"}, {"audio_norm_path": "missing.pt"}]
        )
        extract_per_utterance(
            FakeSpeakerSession(),
            root,
            source_sr=22050,
            batch_size=2,
            num_workers=0,
            fixed_frames=0,
        )
        rows = _read_dataset(root)
        result["missing_manifest"] = {
            "json_paths": [row["speaker_embedding_path"] for row in rows],
            "path_exists": [
                (root / row["speaker_embedding_path"]).exists() for row in rows
            ],
            "evidence": "extract_speaker_embedding.py:547,553-559,581-585,782-791",
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-relative-") as tmp:
        root = Path(tmp)
        (root / "cache").mkdir()
        torch.save(torch.zeros(22050 * 4), root / "cache" / "utt.pt")
        _write_dataset(root, [{"speaker_id": 4, "audio_norm_path": "cache/utt.pt"}])
        out = root / "out"
        extract_from_dataset(
            FakeSpeakerSession(),
            root,
            out,
            max_utterances=1,
            min_duration=0.0,
            source_sr=22050,
        )
        result["relative_dataset_path"] = {
            "expected_output_exists": True,
            "observed_output_exists": (out / "speaker_4.npy").exists(),
            "evidence": "extract_speaker_embedding.py:199-215,237-241; dataset.py:501-505",
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-missing-only-") as tmp:
        root = Path(tmp)
        _write_dataset(root, [{"audio_norm_path": "missing.pt"}])
        extract_per_utterance(FakeSpeakerSession(), root, num_workers=0)
        row = _read_dataset(root)[0]
        result["missing_only_manifest"] = {
            "json_path": row["speaker_embedding_path"],
            "path_exists": (root / row["speaker_embedding_path"]).exists(),
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-empty-cache-") as tmp:
        root = Path(tmp)
        cache = root / "speaker_embeddings"
        cache.mkdir()
        (cache / "empty.npy").touch()
        _write_dataset(root, [{"audio_norm_path": "empty.pt"}])
        session = FakeSpeakerSession()
        extract_per_utterance(session, root, num_workers=0)
        try:
            np.load(cache / "empty.npy", allow_pickle=False)
        except EOFError as exc:
            failure = type(exc).__name__
        else:
            failure = None
        result["empty_cache"] = {
            "encoder_calls": session.calls,
            "json_path": _read_dataset(root)[0]["speaker_embedding_path"],
            "load_failure": failure,
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-stale-") as tmp:
        root = Path(tmp)
        torch.save(torch.zeros(22050), root / "utt.pt")
        _write_dataset(root, [{"audio_norm_path": "utt.pt"}])
        first, second = FakeSpeakerSession(1.0), FakeSpeakerSession(2.0)
        extract_per_utterance(
            first, root, source_sr=22050, num_workers=0, fixed_frames=0
        )
        first_embedding = np.load(root / "speaker_embeddings" / "utt.npy")
        extract_per_utterance(
            second, root, source_sr=22050, num_workers=0, fixed_frames=400
        )
        second_embedding = np.load(root / "speaker_embeddings" / "utt.npy")
        result["stale_cache"] = {
            "first_calls": first.calls,
            "second_calls": second.calls,
            "cache_unchanged": bool(np.array_equal(first_embedding, second_embedding)),
            "evidence": "extract_speaker_embedding.py:531-551",
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-nan-") as tmp:
        root = Path(tmp)
        embedding = np.ones(192, dtype=np.float32)
        embedding[0] = np.nan
        path = root / "bad.npy"
        np.save(path, embedding)
        resolved = _resolve_speaker_embedding(
            speaker_audio=None,
            speaker_encoder=None,
            speaker_embedding_path=str(path),
            speaker_id=None,
            model_path=root / "model.onnx",
            dataset_dir=None,
        )
        result["invalid_direct_npy"] = {
            "shape": list(resolved.shape),
            "finite": bool(np.isfinite(resolved).all()),
            "norm_is_finite": bool(np.isfinite(np.linalg.norm(resolved))),
            "evidence": "infer_onnx.py:459-474",
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-cer-") as tmp:
        root = Path(tmp)
        clips = root / "clips"
        clips.mkdir()
        for name in ("a.wav", "b.wav"):
            with wave.open(str(clips / name), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\0\0" * 160)
        texts = root / "texts.tsv"
        texts.write_text("a\tこんにちは\n", encoding="utf-8")
        captured = {}
        original_builder = eval_cer.build_whisper_transcribe_fn
        original_evaluator = eval_cer.evaluate_clips
        eval_cer.build_whisper_transcribe_fn = lambda *_args: lambda _path: "こんにちは"

        def capture(pairs, transcribe):
            value = original_evaluator(pairs, transcribe)
            captured.update(value)
            return value

        eval_cer.evaluate_clips = capture
        old_argv = sys.argv
        try:
            sys.argv = ["eval_cer", "--clips-dir", str(clips), "--texts", str(texts)]
            with contextlib.redirect_stdout(io.StringIO()):
                return_code = eval_cer.main()
        finally:
            sys.argv = old_argv
            eval_cer.build_whisper_transcribe_fn = original_builder
            eval_cer.evaluate_clips = original_evaluator
        result["cer_missing_clip"] = {
            "return_code": return_code,
            "input_wav_count": 2,
            "matched_text_count": 1,
            "reported_n_clips": captured.get("n_clips"),
            "classification": "score CLI only; formal gate must enforce minimum count",
            "evidence": "eval_cer.py:141-148; zs-eval-contract.md:255-258",
        }

    with tempfile.TemporaryDirectory(prefix="zs-probe-fbank-") as tmp:
        root = Path(tmp)
        rng = np.random.default_rng(0)
        signal = (rng.standard_normal(22050 * 2) * 0.05).astype(np.float32)
        sf.write(root / "utt.wav", signal, 22050, subtype="FLOAT")
        torch.save(torch.from_numpy(signal), root / "utt.pt")
        runtime_fbank = preprocess_audio(root / "utt.wav")
        dataset = _FbankDataset(
            [(0, root / "utt.pt", "utt")], source_sr=22050, fixed_frames=0
        )
        _idx, training_fbank, _stem, valid = dataset[0]
        training_fbank = training_fbank.numpy()
        result["training_runtime_fbank_difference"] = {
            "valid": valid,
            "runtime_shape": list(runtime_fbank.shape),
            "training_shape": list(training_fbank.shape),
            "max_abs_difference": float(np.max(np.abs(runtime_fbank - training_fbank))),
            "rmse": float(np.sqrt(np.mean((runtime_fbank - training_fbank) ** 2))),
            "quality_claim": "preprocessing difference only; real CAM++ quality impact not measured",
            "evidence": "extract_speaker_embedding.py:66-90,281,351-360",
        }

    return result


def original_wavlm_g_gate():
    source = textwrap.dedent(inspect.getsource(VitsModel.training_step_g))
    tree = ast.parse(source)
    tests = [
        node.test
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and "wavlm_every_n_steps" in ast.unparse(node.test)
    ]
    if len(tests) != 1:
        raise RuntimeError("Existing WavLM G gate changed; review the probe")
    return compile(ast.Expression(tests[0]), "<original WavLM G gate>", "eval")


class PairDiscriminator(nn.Module):
    def __init__(self):
        super().__init__()
        self.head = nn.Linear(1, 1)

    def forward(self, real, fake):
        r, f = self.head(real), self.head(fake)
        return [r], [f], [[r]], [[f]]


class ScheduleProbe(pl.LightningModule):
    training_step = VitsModel.training_step

    def __init__(self, d_interval: int, wavlm_interval: int):
        super().__init__()
        self.automatic_optimization = False
        self.save_hyperparameters(
            {
                "d_update_interval": d_interval,
                "grad_clip": None,
                "wavlm_every_n_steps": wavlm_interval,
                "c_wavlm": 0.5,
            }
        )
        self.model_g = nn.Linear(1, 1)
        self.model_d = PairDiscriminator()
        self.model_d_wavlm = PairDiscriminator()
        self.model_d_mrd = self.model_c_spk = None
        self._grad_probe_losses = None
        self._lf_step_active = False
        self.rows = []
        self.d_wavlm_loss_count = 0
        self.gate = original_wavlm_g_gate()

    def configure_optimizers(self):
        return [
            torch.optim.SGD(self.model_g.parameters(), lr=0.01),
            torch.optim.SGD(
                list(self.model_d.parameters()) + list(self.model_d_wavlm.parameters()),
                lr=0.01,
            ),
        ]

    def training_step_g(self, batch):
        self._y = batch[0]
        self._y_hat = self.model_g(batch[0])
        active = eval(self.gate, {"self": self})  # noqa: S307
        self.rows.append(
            {
                "batch": len(self.rows),
                "g_entry_global_step": self.global_step,
                "g_update": self.global_step % self.hparams.d_update_interval == 0,
                "wavlm_g_gate": active,
            }
        )
        loss = self._y_hat.square().mean()
        if active:
            _, fake_scores, _, _ = self.model_d_wavlm(self._y, self._y_hat)
            term, _ = generator_loss(fake_scores)
            loss = loss + term * self.hparams.c_wavlm * self.hparams.wavlm_every_n_steps
        return loss

    def training_step_d(self, batch):
        self.rows[-1]["d_entry_global_step"] = self.global_step
        return VitsModel.training_step_d(self, batch)

    def _disc_autocast_ctx(self):
        return nullcontext()

    def _ddp_synced_is_finite(self, loss):
        return VitsModel._ddp_synced_is_finite(loss)

    def _log_with_batch_info(self, name, *_args, **_kwargs):
        if name == "loss_disc_wavlm":
            self.d_wavlm_loss_count += 1


def run_case(d_interval: int, wavlm_interval: int) -> dict:
    torch.manual_seed(1234)
    model = ScheduleProbe(d_interval, wavlm_interval)
    before = [p.detach().clone() for p in model.model_d_wavlm.parameters()]
    trainer = pl.Trainer(
        accelerator="cpu",
        devices=1,
        max_epochs=1,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        num_sanity_val_steps=0,
    )
    trainer.fit(model, DataLoader(TensorDataset(torch.ones(8, 1)), batch_size=1))
    delta = max(
        float((a - b.detach()).abs().max())
        for a, b in zip(before, model.model_d_wavlm.parameters(), strict=True)
    )
    return {
        "d_update_interval": d_interval,
        "wavlm_every_n_steps": wavlm_interval,
        "batches": len(model.rows),
        "g_updates": sum(r["g_update"] for r in model.rows),
        "d_updates": len(model.rows),
        "final_global_step": model.global_step,
        "wavlm_g_count": sum(r["wavlm_g_gate"] for r in model.rows),
        "wavlm_d_count": model.d_wavlm_loss_count,
        "wavlm_head_max_abs_change": delta,
        "rows": model.rows,
    }


def inspect_archive(archive: Path) -> dict:

    result = {
        "path": archive.as_posix(),
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "method": "TFRecord framing and Event protobuf; CRC not revalidated",
        "runs": [],
    }
    keys = (
        "c_wavlm",
        "d_update_interval",
        "use_wavlm_discriminator",
        "wavlm_every_n_steps",
    )
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if "lightning_logs/version_" not in member.name or not member.name.endswith(
                "hparams.yaml"
            ):
                continue
            with tar.extractfile(member) as f:
                # Lightning YAML includes Python tuple tags. Read only the
                # selected scalar settings without constructing other nodes.
                params = {
                    key.value: yaml.safe_load(value.value)
                    for key, value in yaml.compose(f).value
                    if key.value in keys
                }
            parent = member.name.rsplit("/", 1)[0]
            counts = Counter()
            event_members = []
            for event_member in tar.getmembers():
                if not event_member.name.startswith(parent + "/events.out.tfevents."):
                    continue
                event_members.append(event_member.name)
                with tar.extractfile(event_member) as f:
                    while header := f.read(12):
                        if len(header) != 12:
                            raise ValueError("Truncated TFRecord header")
                        length = struct.unpack("<Q", header[:8])[0]
                        payload, crc = f.read(length), f.read(4)
                        if len(payload) != length or len(crc) != 4:
                            raise ValueError("Truncated TFRecord payload")
                        event = Event.FromString(payload)
                        counts.update(value.tag for value in event.summary.value)
            result["runs"].append(
                {
                    "run": parent,
                    "hparams": {key: params.get(key) for key in keys},
                    "events": event_members,
                    "wavlm_tag_counts": {
                        key: counts[key]
                        for key in (
                            "loss_gen_wavlm",
                            "loss_fm_wavlm",
                            "loss_disc_wavlm",
                        )
                    },
                }
            )
    return result


def evaluation_checks() -> dict:
    # The actual fixed-text loader does not populate either embedding field.
    with tempfile.TemporaryDirectory(prefix="piper-zs-audit-") as temp:
        fixture = Path(temp) / "test_utterances.jsonl"
        fixture.write_text(
            json.dumps(
                {
                    "text": "test",
                    "phoneme_ids": [1, 2],
                    "speaker_embedding": [1.0] * 192,
                    "speaker_embedding_path": "speaker_embeddings/test.npy",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        utt = VitsModel._load_test_dataset(SimpleNamespace(), fixture)[0]
        fixed = {
            "speaker_embedding": getattr(utt, "speaker_embedding", None),
            "speaker_embedding_path": utt.speaker_embedding_path,
        }

    f0 = SimpleNamespace(training=False)
    f0._predicted_f0_hz = lambda *_args: torch.full((64, 1, 1), 2.0)
    torch.manual_seed(1234)
    mixed = SynthesizerTrn._f0_for_decoder(f0, torch.ones(64, 1, 1), None, None, 0.5)

    # Keep original validation_step and guard; replace numerical G/D losses.
    guard = SimpleNamespace(
        training=False,
        global_step=0,
        _kl_cap_consecutive=0,
        _kl_cap_abort_steps=3,
        log=lambda *_args, **_kwargs: None,
        _log_with_batch_info=lambda *_args, **_kwargs: None,
        raw_kl=20000.0,
    )

    def g(_batch):
        VitsModel._update_kl_cap_guard(guard, guard.raw_kl)
        return torch.tensor(1.0)

    guard.training_step_g = g
    guard.training_step_d = lambda _batch: torch.tensor(2.0)
    rows = []
    for index in range(3):
        try:
            VitsModel.validation_step(guard, None, index)
            rows.append({"counter": guard._kl_cap_consecutive, "abort": False})
        except RuntimeError as exc:
            rows.append({"counter": guard._kl_cap_consecutive, "abort": str(exc)})
    guard.raw_kl = 1.0
    VitsModel.validation_step(guard, None, 3)
    return {
        "fixed_loader_ignored_embedding": fixed,
        "eval_f0_gt_1_pred_2_probability_0_5": sorted(mixed.unique().tolist()),
        "eval_kl_guard_abort_threshold_3": rows,
        "eval_kl_guard_counter_after_low_kl": guard._kl_cap_consecutive,
        "kl_method": "Original validation_step and KL guard; numerical G/D losses replaced. Unguarded production G call verified separately at lightning.py:1971.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--v11-archive", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    source = ROOT / "src/python/piper_train/vits/lightning.py"
    result = {
        "torch": torch.__version__,
        "pytorch_lightning": pl.__version__,
        "device": "cpu",
        "source": source.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "method": __doc__,
        "cases": [run_case(d, w) for d, w in [(1, 2), (2, 2), (3, 2), (1, 1)]],
        "evaluation_checks": evaluation_checks(),
        "pipeline_probes": pipeline_probes(),
    }
    if args.v11_archive:
        result["v11_archive"] = inspect_archive(args.v11_archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")
    for case in result["cases"]:
        print(json.dumps({k: v for k, v in case.items() if k != "rows"}))


if __name__ == "__main__":
    main()
