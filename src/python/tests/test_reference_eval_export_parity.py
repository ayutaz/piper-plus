"""参照 spec の export 契約と評価経路の通し試験 (参照融合計画 §8 Task 11R)。

固定する契約 (Task 8R の export と Task 9R の評価を実コードで繋ぐ):

* 実 export (``export_onnx.main``) した ref_spec ONNX の ``<model>.onnx.json`` は、
  評価 (``generate_eval_audio``) の ONNX 契約検査をそのまま通る。block の
  field は評価が検査する集合とちょうど一致し、1 field でも書き換えると拒否される。
* 同じ tiny ref_spec checkpoint・同じ manifest で、``torch-raw`` と ``onnx`` の
  評価出力が許容誤差内で一致する。
* checkpoint の学習 frontend と manifest の frontend が違えば、torch / ONNX の
  どちらの経路でも拒否する。
* 評価の参照 spec の先頭切り出し (Ruling R15) は、学習の検証 (VitsModel の
  ``on_before_batch_transfer``、eval mode) と同じ結果になる。

tiny な ``VitsModel`` を実際に学習 checkpoint として保存し、export・評価を CLI と
同じ関数で通す (モックで置き換えない)。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")
pytest.importorskip("onnx", reason="onnx required")
pytest.importorskip("onnxruntime", reason="onnxruntime required")
pytest.importorskip("soxr", reason="reference spec frontend requires soxr")
pytest.importorskip("soundfile", reason="reference WAV fixtures need soundfile")

pytestmark = [pytest.mark.unit, pytest.mark.inference]

SR = 22050
N_SYMBOLS = 40
TRAINING_FRONTEND = "no-vad;soxr-mq"
OTHER_FRONTEND = "energy-vad@16k;soxr-hq"
# 参照 WAV (約 1.7 s → 約 143 frame) より短くして、評価の先頭切り出しが効く長さ
MAX_FRAMES = 48
STFT = {"filter_length": 1024, "hop_length": 256, "win_length": 1024}
PHONEMES = [1] + [10] * 8 + [2]
# noise_scale / noise_scale_w = 0: torch (乱数 stream) と ORT (別の乱数 stream)
# のどちらも乱数を出力に使わない決定的な合成にする (export も --no-stochastic)
SCALES = [0.0, 1.0, 0.0]

# torch-raw と ORT (FP32) の評価出力の一致の許容誤差。両者は同じ fp32 演算を
# 別 kernel (畳み込みの加算順・GEMM の blocking・erf/exp の近似) で実行し、
# torch 側は weight_norm を毎回 g·v/‖v‖ で組み立てる (export は事前に融合) ので、
# 1 op あたり相対 ~1e-7 (fp32 の ulp) の丸め差が出る。tiny decoder (振幅 O(1)
# 以下) の数百段を通っても ~1e-6..1e-5 に収まり、1e-4 はその 10 倍以上の余裕
# (Task 8R の torch↔ORT parity と同じ根拠・同じ値)。参照の断線をこの許容誤差で
# 見逃さないことは test_onnx_reference_input_changes_output が別に確かめる
# (参照だけが違う 2 clip の差 > 10 × atol)。
PARITY_ATOL = 1e-4


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _tiny_ref_spec_model(**overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    model = VitsModel(
        num_symbols=N_SYMBOLS,
        num_speakers=2,
        num_languages=2,
        dataset=None,
        batch_size=2,
        use_wavlm_discriminator=False,
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
        upsample_initial_channel=64,
        inter_channels=32,
        hidden_channels=32,
        filter_channels=64,
        n_layers=2,
        gin_channels=64,
        prosody_dim=0,
        sample_rate=SR,
        reference_conditioning="ref_spec",
        generator_reference="cross_utt",
        reference_spec_frontend=TRAINING_FRONTEND,
        reference_max_frames=MAX_FRAMES,
        **overrides,
    )
    # 最終層は zero-init (出力 0) なので、そのままでは参照入力が断線していても
    # 一致してしまう。学習済みらしく値を入れる
    with torch.no_grad():
        torch.manual_seed(1)
        model.model_g.reference_encoder.out.weight.normal_(0.0, 0.1)
        model.model_g.reference_encoder.out.bias.normal_(0.0, 0.1)
    return model


def _save_ckpt(model, path: Path) -> Path:
    torch.save(
        {
            "state_dict": model.state_dict(),
            "hyper_parameters": dict(model.hparams),
            "pytorch-lightning_version": "2.0.0",
            "epoch": 40,
        },
        path,
    )
    return path


def _export(ckpt: Path, onnx_path: Path, config: Path) -> Path:
    from piper_train import export_onnx

    saved = sys.argv
    sys.argv = [
        "piper_train.export_onnx",
        str(ckpt),
        str(onnx_path),
        "--no-stochastic",
        "--no-fp16",
        "--config",
        str(config),
    ]
    try:
        export_onnx.main()
    finally:
        sys.argv = saved
    return onnx_path


def _voiced(sr, *, freq, seed, lead=0.4, voiced=0.8, tail=0.5):
    rng = np.random.default_rng(seed)
    n = round(voiced * sr)
    t = np.arange(n) / sr
    body = 0.3 * np.sin(2 * np.pi * freq * t) + 0.01 * rng.standard_normal(n)
    return np.concatenate(
        [np.zeros(int(lead * sr)), body, np.zeros(int(tail * sr))]
    ).astype(np.float32)


def _write_inputs(root: Path) -> Path:
    import soundfile as sf

    sf.write(str(root / "ref_a.wav"), _voiced(SR, freq=220.0, seed=1), SR, "FLOAT")
    sf.write(
        str(root / "ref_b.wav"), _voiced(44100, freq=330.0, seed=2), 44100, "FLOAT"
    )
    np.save(root / "reference.npy", np.arange(1, 193, dtype=np.float32))
    source = root / "test.jsonl"
    rows = [
        {
            "id": f"t{i}",
            "text": "こんにちは",
            "phoneme_ids": PHONEMES,
            "language_id": 0,
            "speaker_id": 0,
            "speaker_embedding_path": "reference.npy",
            "reference_audio_paths": [ref],
        }
        for i, ref in enumerate(["ref_a.wav", "ref_b.wav"])
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return source


def _manifest(source: Path, output: Path, models: dict, frontend: str) -> dict:
    from piper_train.evaluation_manifest import create_manifest

    return create_manifest(
        source_path=source,
        output_path=output,
        models=models,
        sample_rate=SR,
        asr_revision="a" * 40,
        source_revision="b" * 40,
        scales=SCALES,
        reference_spec={"frontend": frontend, **STFT},
    )


def _read_wav(path: Path) -> np.ndarray:
    from piper_train.vits.wavfile import read

    sample_rate, audio = read(path)
    assert sample_rate == SR
    return audio


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    """tiny ref_spec checkpoint・実 export・manifest・torch-raw / onnx の評価出力。"""
    from piper_train.tools import generate_eval_audio as generation

    root = tmp_path_factory.mktemp("ref_eval_parity")
    model = _tiny_ref_spec_model()
    ckpt = _save_ckpt(model, root / "ref.ckpt")
    config = root / "config.json"
    config.write_text(
        json.dumps({"audio": {"sample_rate": SR}, "num_symbols": N_SYMBOLS}),
        encoding="utf-8",
    )
    onnx_path = _export(ckpt, root / "ref.onnx", config)
    source = _write_inputs(root)
    manifest_path = root / "manifest.json"
    manifest = _manifest(
        source,
        manifest_path,
        {"torch-raw": ckpt, "onnx": onnx_path},
        TRAINING_FRONTEND,
    )
    reports = {}
    for backend in ("torch-raw", "onnx"):
        reports[backend] = generation.generate_audio(
            manifest_path, backend, root / f"out-{backend}", device="cpu"
        )
    return {
        "root": root,
        "model": model,
        "ckpt": ckpt,
        "onnx": onnx_path,
        "source": source,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "reports": reports,
    }


def _exported_block(setup) -> dict:
    config = json.loads(Path(str(setup["onnx"]) + ".json").read_text(encoding="utf-8"))
    return config["reference_conditioning"]


# ---------------------------------------------------------------------------
# 実 export の config が評価の ONNX 契約を通る
# ---------------------------------------------------------------------------


class TestExportConfigMeetsEvalContract:
    def test_block_fields_are_exactly_the_eval_contract_fields(self, setup):
        from piper_train.tools import generate_eval_audio as generation

        assert set(_exported_block(setup)) == set(generation._ONNX_BLOCK_FIELDS)

    def test_block_declares_the_training_hparams(self, setup):
        block = _exported_block(setup)
        assert block["frontend"] == TRAINING_FRONTEND
        assert block["max_frames"] == MAX_FRAMES

    def test_onnx_eval_accepts_the_real_export(self, setup):
        contract = setup["reports"]["onnx"]["reference_spec"]["model_contract"]
        assert contract["source"] == str(Path(str(setup["onnx"]) + ".json").resolve())
        assert contract["frontend"] == TRAINING_FRONTEND
        assert contract["max_frames"] == MAX_FRAMES

    @pytest.mark.parametrize(
        "field,value",
        [
            ("schema", "capacity_v1"),
            ("spec_channels", 257),
            ("filter_length", 2048),
            ("hop_length", 128),
            ("win_length", 512),
            ("sample_rate", 16000),
            ("center", True),
            ("frontend", OTHER_FRONTEND),
            ("max_frames", 0),
        ],
    )
    def test_mutated_block_field_is_refused(self, setup, tmp_path, field, value):
        from piper_train.tools import generate_eval_audio as generation

        block = _exported_block(setup)
        assert field in block and block[field] != value
        onnx_copy = tmp_path / "ref.onnx"
        shutil.copyfile(setup["onnx"], onnx_copy)
        config = json.loads(
            Path(str(setup["onnx"]) + ".json").read_text(encoding="utf-8")
        )
        config["reference_conditioning"][field] = value
        Path(str(onnx_copy) + ".json").write_text(json.dumps(config), "utf-8")
        manifest_path = tmp_path / "manifest.json"
        _manifest(
            setup["source"], manifest_path, {"onnx": onnx_copy}, TRAINING_FRONTEND
        )
        output = tmp_path / "out"
        with pytest.raises(ValueError, match=field):
            generation.generate_audio(manifest_path, "onnx", output)
        assert not (output / "generation.json").exists()


# ---------------------------------------------------------------------------
# torch-raw ↔ onnx
# ---------------------------------------------------------------------------


class TestTorchOnnxParity:
    def test_torch_raw_and_onnx_have_same_length(self, setup):
        root = setup["root"]
        for clip in setup["manifest"]["clips"]:
            torch_wav = _read_wav(root / "out-torch-raw" / f"{clip['id']}.wav")
            onnx_wav = _read_wav(root / "out-onnx" / f"{clip['id']}.wav")
            assert torch_wav.shape == onnx_wav.shape

    def test_torch_raw_and_onnx_audio_match(self, setup):
        root = setup["root"]
        for clip in setup["manifest"]["clips"]:
            torch_wav = _read_wav(root / "out-torch-raw" / f"{clip['id']}.wav")
            onnx_wav = _read_wav(root / "out-onnx" / f"{clip['id']}.wav")
            np.testing.assert_allclose(onnx_wav, torch_wav, rtol=0, atol=PARITY_ATOL)

    def test_onnx_reference_input_changes_output(self, setup):
        # 2 clip は参照 WAV だけが違う。その差が parity の許容誤差より十分大きい
        # (参照の断線を parity が見逃さない)
        root = setup["root"]
        first, second = (
            _read_wav(root / "out-onnx" / f"{clip['id']}.wav")
            for clip in setup["manifest"]["clips"]
        )
        assert first.shape != second.shape or (
            np.max(np.abs(first - second)) > 10 * PARITY_ATOL
        )

    def test_both_backends_feed_the_same_cropped_frames(self, setup):
        for backend in ("torch-raw", "onnx"):
            for clip in setup["reports"][backend]["clips"]:
                assert clip["reference_spec"]["frames"] > MAX_FRAMES
                assert clip["reference_spec"]["fed_frames"] == MAX_FRAMES


# ---------------------------------------------------------------------------
# frontend の食い違い
# ---------------------------------------------------------------------------


class TestFrontendMismatch:
    @pytest.mark.parametrize("backend", ["torch-raw", "onnx"])
    def test_manifest_frontend_differing_from_checkpoint_is_refused(
        self, setup, tmp_path, backend
    ):
        from piper_train.tools import generate_eval_audio as generation

        path = setup["ckpt"] if backend == "torch-raw" else setup["onnx"]
        manifest_path = tmp_path / "manifest.json"
        _manifest(setup["source"], manifest_path, {backend: path}, OTHER_FRONTEND)
        output = tmp_path / "out"
        with pytest.raises(ValueError, match="frontend mismatch"):
            generation.generate_audio(manifest_path, backend, output, device="cpu")
        assert not (output / "generation.json").exists()


# ---------------------------------------------------------------------------
# 評価の先頭切り出し = 学習の検証の切り出し
# ---------------------------------------------------------------------------


def _validation_crop(model, spec: torch.Tensor) -> torch.Tensor:
    """学習の検証 (eval mode の on_before_batch_transfer) が G に渡す参照 spec。"""
    from piper_train.vits.dataset import Batch

    batch = Batch(
        phoneme_ids=torch.ones(1, 3, dtype=torch.long),
        phoneme_lengths=torch.tensor([3]),
        spectrograms=torch.zeros(1, 513, 4),
        spectrogram_lengths=torch.tensor([4]),
        audios=torch.zeros(1, 1, 1024),
        audio_lengths=torch.tensor([1024]),
        utterance_ids=["target"],
        reference_specs=spec[None],
        reference_spec_lengths=torch.tensor([spec.shape[-1]]),
    )
    model.eval()
    out = model.on_before_batch_transfer(batch, 0)
    length = int(out.reference_spec_lengths[0])
    return out.reference_specs[0, :, :length]


class TestHeadCropMatchesValidation:
    def test_eval_crop_equals_validation_crop(self, setup):
        from piper_train.tools import generate_eval_audio as generation

        for clip in setup["manifest"]["clips"]:
            stored = np.load(clip["reference_spec"]["spec_path"], allow_pickle=False)
            expected = _validation_crop(setup["model"], torch.from_numpy(stored))
            fed = generation._head_crop(stored, MAX_FRAMES)
            assert torch.equal(torch.from_numpy(fed), expected)

    def test_torch_eval_output_uses_the_validation_crop(self, setup):
        # torch-raw の評価 WAV = 学習の検証と同じ切り出しの spec で直接 infer した
        # 出力 (同じ CPU 演算列・同じ seed なので bit 一致)
        from piper_plus.embedding import validate_embedding
        from piper_train.inference_eval import isolated_inference
        from piper_train.tools import generate_eval_audio as generation

        generator, _checkpoint, _rate = generation.load_torch_generator(
            setup["ckpt"], device="cpu"
        )
        embedding = validate_embedding(np.arange(1, 193, dtype=np.float32), 192)
        for ordinal, clip in enumerate(setup["manifest"]["clips"]):
            stored = np.load(clip["reference_spec"]["spec_path"], allow_pickle=False)
            spec = _validation_crop(setup["model"], torch.from_numpy(stored))
            with isolated_inference(generator, setup["manifest"]["seed"] + ordinal):
                audio = generator.infer(
                    torch.tensor([clip["phoneme_ids"]]),
                    torch.tensor([len(clip["phoneme_ids"])]),
                    speaker_embeddings=torch.from_numpy(embedding[None, :]),
                    lid=torch.tensor([clip["language_id"]]),
                    sid=torch.tensor([clip["speaker_id"]]),
                    noise_scale=SCALES[0],
                    length_scale=SCALES[1],
                    noise_scale_w=SCALES[2],
                    reference_spec=spec[None].contiguous(),
                    reference_spec_lengths=torch.tensor([spec.shape[-1]]),
                )[0]
            expected = audio.detach().cpu().numpy().reshape(-1).astype(np.float32)
            np.testing.assert_array_equal(
                _read_wav(setup["root"] / "out-torch-raw" / f"{clip['id']}.wav"),
                expected,
            )
