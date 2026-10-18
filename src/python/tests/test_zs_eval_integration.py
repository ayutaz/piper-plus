"""Phase A 契約ゲート統合テスト (再発防止面の登録・配線の存在検証).

zs-prevention gate (scripts/check_zs_prevention_tests.py) の EXPECTED に
Phase A の新指標 (コム / 韻律 / 帯域プロファイル + isolation gate) が登録され、
契約 (docs/spec/zs-eval-contract.md) と pre-commit 配線が揃っていることを pin
する (docs/design/zero-shot-v10b-quality-plan.md §2 E-7/E-8 /
phase_a_spec.md §5.1 §5.3 §5.4)。

教訓① (評価メトリクスの学習流用禁止) の三重固定:
(i) モジュール docstring の EVAL-ONLY マーカー / (ii) 契約 §2 禁止事項 4 /
(iii) pre-commit gate — の (ii)(iii) 側の登録をここで検証する。
((i) と gate 本体の挙動は test_zs_metric_isolation_gate.py が担当。)
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PREVENTION_PATH = REPO_ROOT / "scripts" / "check_zs_prevention_tests.py"
CONTRACT_PATH = REPO_ROOT / "docs" / "spec" / "zs-eval-contract.md"
PRECOMMIT_PATH = REPO_ROOT / ".pre-commit-config.yaml"


@pytest.fixture(scope="module")
def prevention():
    """prevention gate script を module として load する (非汎用 module 名)。"""
    spec = importlib.util.spec_from_file_location(
        "zs_prevention_gate_module", PREVENTION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load {PREVENTION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestPreventionGateExpected:
    """§5.4: EXPECTED への新指標シンボル登録 (黙った弱体化の検出面を先に固定)。"""

    def test_new_metric_modules_registered(self, prevention):
        exp = prevention.EXPECTED

        comb = exp["src/python/piper_train/tools/measure_comb_artifacts.py"]
        assert "def comb_metrics" in comb
        assert "EVAL-ONLY" in comb

        pros = exp["src/python/piper_train/tools/measure_prosody.py"]
        assert "def prosody_stats" in pros
        assert "def prosody_delta" in pros
        assert "EVAL-ONLY" in pros

        band = exp["src/python/piper_train/tools/measure_band_noise.py"]
        assert "def voiced_high_band_excess" in band  # 旧指標の互換維持
        assert "def band_profile" in band  # E-1 帯域ベクトル
        assert "EVAL-ONLY" in band

    def test_isolation_gate_registered(self, prevention):
        gate = prevention.EXPECTED["scripts/check_zs_metric_isolation.py"]
        assert "piper_train.vits" in gate  # 隔離 gate 本体の存在ガード

    def test_new_prevention_tests_registered(self, prevention):
        exp = prevention.EXPECTED

        comb_t = exp["src/python/tests/test_measure_comb_artifacts.py"]
        for sym in (
            "def test_off_grid_tones_do_not_trip",  # 格子選択性 (偽陽性防止)
            "def test_white_noise_excess_near_zero",  # ゼロ点校正
            "def test_frame_tiled_noise_high_autocorr",  # フレーム格子検出能力
        ):
            assert sym in comb_t, sym

        pros_t = exp["src/python/tests/test_measure_prosody.py"]
        for sym in (
            "def test_vibrato_f0_std_matches_first_principles",
            "def test_flat_f0_near_zero_std",
        ):
            assert sym in pros_t, sym

    def test_eval_and_contract_symbols_extended(self, prevention):
        exp = prevention.EXPECTED

        ev = exp["src/python/piper_train/tools/eval_zs_secs.py"]
        assert "above_ceiling" in ev  # E-7(iii)
        assert "manifest" in ev  # E-5(i)
        # 既存ガード面が残っていること (置換ではなく追加)
        for legacy in (
            "goodhart_flag",
            "require-encoder2",
            "gap_same_minus_cross",
            "cross_utt_secs",
        ):
            assert legacy in ev, legacy

        doc = exp["docs/spec/zs-eval-contract.md"]
        assert "恒久禁止" in doc  # §2 禁止事項 4 (学習流用の恒久禁止)
        assert "above_ceiling_flag" in doc
        assert "same-utt" in doc  # 既存条項の維持


@pytest.mark.unit
class TestContractText:
    """§5.1: 契約本文への Phase A 追記 (禁止事項 4-5 / v3 schema / 音響指標)。"""

    def test_contract_bans_metric_reuse_in_training(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        # 禁止事項 4: 評価メトリクスの学習流用の恒久禁止 + 機械的強制の参照
        assert "学習流用" in text
        assert "check_zs_metric_isolation" in text
        # 禁止事項 5: 素の出力 wav で測る (gate 回避目的の後処理禁止)
        assert "後処理" in text

    def test_contract_defines_v3_schema_and_flags(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        assert "zs-eval-v3" in text
        assert "above_ceiling_flag" in text
        # E-7(ii): SECS↔人間類似の相関上限の注記 (±0.03 未満は判定材料にしない)
        assert "0.03" in text

    def test_contract_registers_acoustic_metrics(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        assert "comb_excess_db" in text  # E-4 コム超過
        assert "prosody_delta" in text  # E-3 韻律記述統計差
        assert "band_profile" in text  # E-1 帯域プロファイル


@pytest.mark.unit
class TestPreCommitWiring:
    """§5.3 / §5.4: gate の pre-commit 配線 (登録漏れ = gate は存在しても走らない)。"""

    def test_isolation_gate_wired(self):
        text = PRECOMMIT_PATH.read_text(encoding="utf-8")
        assert "zs-metric-isolation-gate" in text
        assert "check_zs_metric_isolation.py" in text

    def test_prevention_gate_files_regex_extended(self):
        text = PRECOMMIT_PATH.read_text(encoding="utf-8")
        # 新モジュール / 新テストの変更でも zs-prevention-gate が発火すること
        assert "measure_comb_artifacts" in text
        assert "measure_prosody" in text


@pytest.mark.unit
def test_prevention_gate_full_run_passes():
    """prevention gate 自体が現 repo で green であること。

    EXPECTED 追記 (red) → モジュール/契約の実装 (green) の順序を強制する:
    EXPECTED だけ先に更新した状態では本テストが red になり、シンボル実装まで
    commit できない (実装完了時点で green に戻る)。
    """
    proc = subprocess.run(
        [sys.executable, str(PREVENTION_PATH)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


# ---------------------------------------------------------------------------
# Task 9R: 評価経路の参照 spec feed と来歴
# (docs/design/zero-shot-reference-fusion-plan-2026-10-17.md §8 Task 9R)
#
# ref_spec モデルの評価では manifest の参照 WAV から学習 cache と同じ frontend
# で線形振幅 spec を作って feed し、frontend・参照音声 hash・spec hash・T_ref を
# manifest と生成 report に記録する。none / capacity モデルの評価出力は変えない。
# ---------------------------------------------------------------------------

import json  # noqa: E402

import numpy as np  # noqa: E402


SR = 22050
STFT = {"filter_length": 1024, "hop_length": 256, "win_length": 1024}
PHONEMES = [1] + [10] * 8 + [2]
# 変更前 (6904ef0e) の generation.json の key 集合 (旧モデルの report schema)
LEGACY_REPORT_KEYS = {
    "version",
    "backend",
    "execution_device",
    "manifest_sha256",
    "conditions_sha256",
    "model_sha256",
    "source",
    "sample_rate",
    "scales",
    "seed",
    "training_epoch",
    "ema_applied",
    "ground_truth_f0_or_duration",
    "audio_encoding",
    "clips",
}
LEGACY_CLIP_KEYS = {
    "id",
    "text_sha256",
    "speaker_embedding_sha256",
    "reference_audio",
    "seed",
    "wav_sha256",
}


def _voiced(sr, *, freq, seed, lead=0.4, voiced=0.8, tail=0.5):
    rng = np.random.default_rng(seed)
    n = int(round(voiced * sr))
    t = np.arange(n) / sr
    body = 0.3 * np.sin(2 * np.pi * freq * t) + 0.01 * rng.standard_normal(n)
    return np.concatenate(
        [np.zeros(int(lead * sr)), body, np.zeros(int(tail * sr))]
    ).astype(np.float32)


def _write_wav(path, audio, sr):
    import soundfile as sf

    sf.write(str(path), audio, sr, subtype="FLOAT")
    return path


def _write_rows(source, rows):
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def frontend_deps():
    """参照 spec frontend の依存 (torch / soxr)。Windows CI (torch なし) では skip。"""
    pytest.importorskip("torch", reason="reference spec frontend requires torch")
    pytest.importorskip("soxr", reason="reference spec frontend requires soxr")


@pytest.fixture
def ref_eval_inputs(tmp_path):
    """参照 WAV 2 本 (22.05k / 44.1k)・埋め込み・2 clip の評価入力。"""
    _write_wav(tmp_path / "ref_a.wav", _voiced(SR, freq=220.0, seed=1), SR)
    _write_wav(tmp_path / "ref_b.wav", _voiced(44100, freq=330.0, seed=2), 44100)
    np.save(tmp_path / "reference.npy", np.arange(1, 193, dtype=np.float32))
    rows = [
        {
            "id": f"t{i}",
            "text": text,
            "phoneme_ids": PHONEMES,
            "language_id": 0,
            "speaker_id": 0,
            "speaker_embedding_path": "reference.npy",
            "reference_audio_paths": [ref],
        }
        for i, (text, ref) in enumerate(
            [("こんにちは", "ref_a.wav"), ("ありがとう", "ref_b.wav")]
        )
    ]
    source = tmp_path / "test.jsonl"
    _write_rows(source, rows)
    options = {
        "source_path": source,
        "output_path": tmp_path / "manifest.json",
        "sample_rate": SR,
        "asr_revision": "a" * 40,
        "source_revision": "b" * 40,
    }
    return source, rows, options


def _tiny_vits(monkeypatch, mode, *, seed=0):
    torch = pytest.importorskip("torch", reason="real tiny VITS")
    pytest.importorskip("pytorch_lightning", reason="real checkpoint loading")
    from piper_train.vits import lightning

    monkeypatch.setattr(
        lightning, "MultiPeriodDiscriminator", lambda **kwargs: torch.nn.Linear(1, 1)
    )
    torch.manual_seed(seed)
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
        reference_conditioning=mode,
    )
    module = {"ref_spec": "reference_encoder", "capacity": "capacity_control"}.get(
        mode
    )
    if module is not None:
        # 最終層 zero-init のままでは参照入力が出力に効かず、feed の検証に
        # ならない (旧モデルとも区別できない) ので乱数で埋める
        generator = torch.Generator().manual_seed(seed + 1)
        out = getattr(model.model_g, module).out
        with torch.no_grad():
            out.weight.copy_(torch.randn(out.weight.shape, generator=generator))
            out.bias.copy_(torch.randn(out.bias.shape, generator=generator))
    return model


def _save_checkpoint(model, path):
    import torch

    torch.save(
        {
            "hyper_parameters": dict(model.hparams),
            "state_dict": model.state_dict(),
            "epoch": 40,
        },
        path,
    )
    return path


def _prepare(options, models, *, reference_spec=None, **overrides):
    from piper_train.evaluation_manifest import create_manifest

    # 既定経路は旧 API (reference_spec 引数なし) と同じ呼び出しにする
    extra = {} if reference_spec is None else {"reference_spec": reference_spec}
    return create_manifest(**{**options, **overrides}, models=models, **extra)


def _reference_defaults():
    from piper_train.evaluation_manifest import REFERENCE_SPEC_DEFAULTS

    assert REFERENCE_SPEC_DEFAULTS == STFT  # 学習 hparams の既定と同じ契約値
    return dict(REFERENCE_SPEC_DEFAULTS)


def _read_wav(path):
    from piper_train.vits.wavfile import read

    sample_rate, audio = read(path)
    assert sample_rate == SR
    return audio


def _direct_infer(generator, clip, seed, reference_spec=None):
    """generate_eval_audio を通さず、同じ条件で infer を直接呼ぶ (独立参照)。"""
    import torch

    from piper_plus.embedding import validate_embedding
    from piper_train.inference_eval import isolated_inference

    embedding = validate_embedding(np.arange(1, 193, dtype=np.float32), 192)
    kwargs = {
        "speaker_embeddings": torch.from_numpy(embedding[None, :]),
        "lid": torch.tensor([clip["language_id"]]),
        "sid": torch.tensor([clip["speaker_id"]]),
        "noise_scale": 0.4,
        "length_scale": 1.0,
        "noise_scale_w": 0.5,
    }
    if reference_spec is not None:
        kwargs["reference_spec"] = reference_spec[None]
        kwargs["reference_spec_lengths"] = torch.tensor(
            [reference_spec.shape[-1]], dtype=torch.long
        )
    with isolated_inference(generator, seed):
        audio = generator.infer(
            torch.tensor([clip["phoneme_ids"]]),
            torch.tensor([len(clip["phoneme_ids"])]),
            **kwargs,
        )[0]
    return audio.detach().cpu().numpy().reshape(-1).astype(np.float32)


def _frontend(path):
    from piper_train.reference_frontend import reference_spec_from_file

    spec, _info = reference_spec_from_file(path, target_sample_rate=SR, **STFT)
    return spec


def _echo_onnx(path, *, spec_channels=513, with_lengths=True):
    """契約の入力名を持ち、``[T_ref, spec.flatten()]`` を output に返す ONNX。

    feed された reference_spec / lengths の中身をそのまま WAV に書き出させ、
    評価経路が frontend の spec を契約の形 ([1, 513, T]、float32 / int64) で
    渡していることを実 ONNX Runtime 上で確かめる (Task 8R の export 前の代用)。
    """
    onnx = pytest.importorskip("onnx", reason="real ONNX fixture")
    pytest.importorskip("onnxruntime", reason="real ONNX fixture")
    helper, tensor = onnx.helper, onnx.TensorProto
    inputs = [
        helper.make_tensor_value_info("input", tensor.INT64, [1, "T"]),
        helper.make_tensor_value_info("input_lengths", tensor.INT64, [1]),
        helper.make_tensor_value_info("scales", tensor.FLOAT, [3]),
        helper.make_tensor_value_info("speaker_embedding", tensor.FLOAT, [1, 192]),
        helper.make_tensor_value_info(
            "reference_spec", tensor.FLOAT, [1, spec_channels, "ref_frames"]
        ),
    ]
    nodes = [
        helper.make_node(
            "Constant",
            [],
            ["flat_shape"],
            value=helper.make_tensor("s", tensor.INT64, [3], [1, 1, -1]),
        ),
        helper.make_node("Reshape", ["reference_spec", "flat_shape"], ["spec_flat"]),
    ]
    if with_lengths:
        inputs.append(
            helper.make_tensor_value_info("reference_spec_lengths", tensor.INT64, [1])
        )
        nodes += [
            helper.make_node(
                "Cast", ["reference_spec_lengths"], ["len_f"], to=tensor.FLOAT
            ),
            helper.make_node("Reshape", ["len_f", "flat_shape"], ["len3"]),
            helper.make_node("Concat", ["len3", "spec_flat"], ["output"], axis=2),
        ]
    else:
        nodes.append(helper.make_node("Identity", ["spec_flat"], ["output"]))
    graph = helper.make_graph(
        nodes,
        "reference-spec-echo",
        inputs,
        [helper.make_tensor_value_info("output", tensor.FLOAT, [1, 1, "N"])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 10
    onnx.save(model, path)
    return path


def _legacy_onnx(path):
    """旧契約の入力だけを持つ ONNX (余計な feed は ORT が invalid input で拒否)。"""
    onnx = pytest.importorskip("onnx", reason="real ONNX fixture")
    pytest.importorskip("onnxruntime", reason="real ONNX fixture")
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
                "ReduceSum",
                ["speaker_embedding"],
                ["sum"],
                keepdims=1,
            ),
            helper.make_node(
                "Constant",
                [],
                ["shape"],
                value=helper.make_tensor("s", tensor.INT64, [3], [1, 1, 1]),
            ),
            helper.make_node("Reshape", ["sum", "shape"], ["output"]),
        ],
        "legacy-fixture",
        inputs,
        [helper.make_tensor_value_info("output", tensor.FLOAT, [1, 1, 1])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 10
    onnx.save(model, path)
    return path


def _rewrite_manifest(path, mutate):
    """manifest を書き換え、conditions hash を付け直す (hash 検査以外を試すため)。"""
    from piper_train.evaluation_manifest import conditions_sha256

    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest["conditions_sha256"] = conditions_sha256(manifest)
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


@pytest.mark.unit
@pytest.mark.usefixtures("frontend_deps")
class TestReferenceSpecManifest:
    """create_manifest / validate_manifest の参照 spec 来歴。"""

    def test_eval_manifest_records_frontend_and_spec_hash(self, ref_eval_inputs):
        from piper_train.embedding_cache import file_sha256
        from piper_train.reference_frontend import reference_spec_sha256

        source, rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
        manifest = _prepare(
            options,
            {"onnx": source.parent / "m.onnx"},
            reference_spec=_reference_defaults(),
        )
        assert manifest["reference_spec"] == {
            "frontend": "energy-vad@16k;soxr-hq",
            **STFT,
            "center": False,
            "trim": True,
        }
        for row, clip in zip(rows, manifest["clips"], strict=True):
            wav = source.parent / row["reference_audio_paths"][0]
            spec = _frontend(wav)
            assert clip["reference_spec"] == {
                "audio_sha256": file_sha256(wav),
                "spec_sha256": reference_spec_sha256(spec),
                "frames": spec.shape[-1],
            }

    def test_manifest_default_has_no_reference_spec_fields(self, ref_eval_inputs):
        # 既定 (reference_spec=None) の manifest schema は変更前と同じ
        source, _rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
        manifest = _prepare(options, {"onnx": source.parent / "m.onnx"})
        assert "reference_spec" not in manifest
        assert all("reference_spec" not in clip for clip in manifest["clips"])

    def test_manifest_reference_spec_is_part_of_conditions_hash(self, ref_eval_inputs):
        source, _rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
        models = {"onnx": source.parent / "m.onnx"}
        legacy = _prepare(options, models)
        with_spec = _prepare(options, models, reference_spec=_reference_defaults())
        assert legacy["conditions_sha256"] != with_spec["conditions_sha256"]

    def test_manifest_reference_spec_requires_reference_audio(self, ref_eval_inputs):
        source, rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
        rows[1].pop("reference_audio_paths")
        _write_rows(source, rows)
        with pytest.raises(ValueError, match="reference audio"):
            _prepare(
                options,
                {"onnx": source.parent / "m.onnx"},
                reference_spec=_reference_defaults(),
            )
        assert not options["output_path"].exists()

    def test_manifest_reference_spec_rejects_silent_reference(self, ref_eval_inputs):
        source, _rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
        _write_wav(source.parent / "ref_b.wav", np.zeros(44100, np.float32), 44100)
        with pytest.raises(ValueError, match="no voiced"):
            _prepare(
                options,
                {"onnx": source.parent / "m.onnx"},
                reference_spec=_reference_defaults(),
            )
        assert not options["output_path"].exists()

    @pytest.mark.parametrize(
        "field,value",
        [("filter_length", 1000), ("hop_length", 0), ("win_length", 2048)],
    )
    def test_manifest_rejects_invalid_reference_stft(
        self, ref_eval_inputs, field, value
    ):
        # filter_length は偶数 (bins = n/2+1)、hop > 0、win <= filter_length
        source, _rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
        with pytest.raises(ValueError, match=field):
            _prepare(
                options,
                {"onnx": source.parent / "m.onnx"},
                reference_spec={**_reference_defaults(), field: value},
            )
        assert not options["output_path"].exists()

    @pytest.mark.parametrize(
        "mutation",
        [
            "frames-zero",
            "frames-bool",
            "spec-sha-not-hex",
            "audio-sha-not-first-reference",
            "unknown-frontend",
            "missing-clip-record",
            "extra-clip-record-without-settings",
            "filter-length-not-int",
            "center-true",
        ],
    )
    def test_validate_manifest_rejects_malformed_reference_spec(
        self, ref_eval_inputs, mutation
    ):
        from piper_train.evaluation_manifest import load_manifest

        source, _rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
        _prepare(
            options,
            {"onnx": source.parent / "m.onnx"},
            reference_spec=_reference_defaults(),
        )

        def mutate(manifest):
            clip = manifest["clips"][0]
            if mutation == "frames-zero":
                clip["reference_spec"]["frames"] = 0
            elif mutation == "frames-bool":
                clip["reference_spec"]["frames"] = True
            elif mutation == "spec-sha-not-hex":
                clip["reference_spec"]["spec_sha256"] = "z" * 64
            elif mutation == "audio-sha-not-first-reference":
                clip["reference_spec"]["audio_sha256"] = manifest["clips"][1][
                    "reference_audio"
                ][0]["sha256"]
            elif mutation == "unknown-frontend":
                manifest["reference_spec"]["frontend"] = "silero-vad;torchaudio"
            elif mutation == "missing-clip-record":
                clip.pop("reference_spec")
            elif mutation == "extra-clip-record-without-settings":
                manifest.pop("reference_spec")
            elif mutation == "filter-length-not-int":
                manifest["reference_spec"]["filter_length"] = 1024.0
            else:
                manifest["reference_spec"]["center"] = True

        _rewrite_manifest(options["output_path"], mutate)
        with pytest.raises(ValueError, match="reference"):
            load_manifest(options["output_path"])

    def test_prepare_cli_reference_spec_flag_records_spec(
        self, ref_eval_inputs, monkeypatch
    ):
        import sys

        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
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
                "--onnx",
                str(source.parent / "m.onnx"),
                "--asr-revision",
                "a" * 40,
                "--source-revision",
                "b" * 40,
                "--reference-spec",
            ],
        )
        assert generation.main() == 0
        manifest = json.loads(options["output_path"].read_text(encoding="utf-8"))
        assert manifest["reference_spec"]["frontend"] == "energy-vad@16k;soxr-hq"
        assert all(clip["reference_spec"]["frames"] > 0 for clip in manifest["clips"])

    def test_prepare_cli_default_records_no_reference_spec(
        self, ref_eval_inputs, monkeypatch
    ):
        import sys

        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        (source.parent / "m.onnx").write_bytes(b"x")
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
                "--onnx",
                str(source.parent / "m.onnx"),
                "--asr-revision",
                "a" * 40,
                "--source-revision",
                "b" * 40,
            ],
        )
        assert generation.main() == 0
        manifest = json.loads(options["output_path"].read_text(encoding="utf-8"))
        assert "reference_spec" not in manifest


@pytest.mark.unit
@pytest.mark.usefixtures("frontend_deps")
class TestReferenceSpecTorchEval:
    """torch backend: ref_spec モデルへの feed と旧モデルの不変性 (実 tiny VITS)。"""

    def test_eval_feeds_reference_spec_for_ref_spec_model(
        self, ref_eval_inputs, monkeypatch
    ):
        from piper_train.tools import generate_eval_audio as generation

        source, rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        _prepare(options, {"torch-raw": ckpt}, reference_spec=_reference_defaults())
        output = source.parent / "out"
        generation.generate_audio(
            options["output_path"], "torch-raw", output, device="cpu"
        )
        loaded, _checkpoint, _rate = generation.load_torch_generator(ckpt, device="cpu")
        for ordinal, row in enumerate(rows):
            expected = _direct_infer(
                loaded,
                row,
                42 + ordinal,
                reference_spec=_frontend(
                    source.parent / row["reference_audio_paths"][0]
                ),
            )
            # 同じ CPU 演算列・同じ seed なので bit 一致を要求する
            np.testing.assert_array_equal(
                _read_wav(output / f"{row['id']}.wav"), expected
            )

    def test_eval_ref_spec_output_depends_on_reference_audio(
        self, ref_eval_inputs, monkeypatch
    ):
        # 参照 WAV だけを差し替えると出力が変わる (spec が実際に消費されている)
        from piper_train.tools import generate_eval_audio as generation

        source, rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        audio = {}
        for ref in ("ref_a.wav", "ref_b.wav"):
            for row in rows:
                row["reference_audio_paths"] = [ref]
            _write_rows(source, rows)
            _prepare(
                options, {"torch-raw": ckpt}, reference_spec=_reference_defaults()
            )
            output = source.parent / f"out-{ref}"
            generation.generate_audio(
                options["output_path"], "torch-raw", output, device="cpu"
            )
            audio[ref] = _read_wav(output / "t0.wav")
        assert not np.array_equal(audio["ref_a.wav"], audio["ref_b.wav"])

    def test_generation_report_records_reference_spec_provenance(
        self, ref_eval_inputs, monkeypatch
    ):
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        manifest = _prepare(
            options, {"torch-raw": ckpt}, reference_spec=_reference_defaults()
        )
        report = generation.generate_audio(
            options["output_path"], "torch-raw", source.parent / "out", device="cpu"
        )
        assert report["reference_spec"] == manifest["reference_spec"]
        for clip, expected in zip(report["clips"], manifest["clips"], strict=True):
            assert clip["reference_spec"] == expected["reference_spec"]
        saved = json.loads(
            (source.parent / "out" / "generation.json").read_text(encoding="utf-8")
        )
        assert saved["reference_spec"] == manifest["reference_spec"]

    def test_eval_ref_spec_model_requires_reference_audio(
        self, ref_eval_inputs, monkeypatch
    ):
        from piper_train.tools import generate_eval_audio as generation

        source, rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        rows[1].pop("reference_audio_paths")
        _write_rows(source, rows)
        _prepare(options, {"torch-raw": ckpt})
        output = source.parent / "out"
        with pytest.raises(ValueError, match="reference audio"):
            generation.generate_audio(
                options["output_path"], "torch-raw", output, device="cpu"
            )
        assert not (output / "generation.json").exists()

    def test_eval_ref_spec_model_requires_manifest_reference_spec(
        self, ref_eval_inputs, monkeypatch
    ):
        # 参照 WAV はあるが prepare 時に spec の来歴を固定していない manifest
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        _prepare(options, {"torch-raw": ckpt})
        output = source.parent / "out"
        with pytest.raises(ValueError, match="--reference-spec"):
            generation.generate_audio(
                options["output_path"], "torch-raw", output, device="cpu"
            )
        assert not (output / "generation.json").exists()

    def test_eval_ref_spec_detects_spec_hash_mismatch(
        self, ref_eval_inputs, monkeypatch
    ):
        # frontend の実装・依存が prepare 時から変わると spec hash が変わる
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        _prepare(options, {"torch-raw": ckpt}, reference_spec=_reference_defaults())

        def mutate(manifest):
            manifest["clips"][1]["reference_spec"]["spec_sha256"] = "0" * 64

        _rewrite_manifest(options["output_path"], mutate)
        output = source.parent / "out"
        with pytest.raises(ValueError, match="reference spec hash"):
            generation.generate_audio(
                options["output_path"], "torch-raw", output, device="cpu"
            )
        assert not (output / "generation.json").exists()

    def test_eval_ref_spec_detects_frames_mismatch(self, ref_eval_inputs, monkeypatch):
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        _prepare(options, {"torch-raw": ckpt}, reference_spec=_reference_defaults())

        def mutate(manifest):
            manifest["clips"][0]["reference_spec"]["frames"] += 1

        _rewrite_manifest(options["output_path"], mutate)
        with pytest.raises(ValueError, match="T_ref"):
            generation.generate_audio(
                options["output_path"], "torch-raw", source.parent / "o", device="cpu"
            )

    def test_eval_ref_spec_rejects_stft_mismatch_with_model(
        self, ref_eval_inputs, monkeypatch
    ):
        # 513 bin のモデルに 257 bin (filter_length 512) の spec を作らない
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        _prepare(
            options,
            {"torch-raw": ckpt},
            reference_spec={"filter_length": 512, "hop_length": 256, "win_length": 512},
        )
        output = source.parent / "out"
        with pytest.raises(ValueError, match="filter_length"):
            generation.generate_audio(
                options["output_path"], "torch-raw", output, device="cpu"
            )
        assert not (output / "generation.json").exists()

    def test_eval_ref_spec_rejects_hop_mismatch_with_checkpoint(
        self, ref_eval_inputs, monkeypatch
    ):
        # bin 数が同じでも hop が学習 hparams と違えば時間軸の解像度が変わる
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(
            _tiny_vits(monkeypatch, "ref_spec"), source.parent / "model.ckpt"
        )
        _prepare(
            options,
            {"torch-raw": ckpt},
            reference_spec={**_reference_defaults(), "hop_length": 128},
        )
        with pytest.raises(ValueError, match="hop_length"):
            generation.generate_audio(
                options["output_path"], "torch-raw", source.parent / "o", device="cpu"
            )

    @pytest.mark.parametrize("mode", ["none", "capacity"])
    def test_eval_legacy_model_unchanged(self, ref_eval_inputs, monkeypatch, mode):
        # 旧経路 (参照 spec を渡さない infer) と bit 一致
        from piper_train.tools import generate_eval_audio as generation

        source, rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(_tiny_vits(monkeypatch, mode), source.parent / "m.ckpt")
        _prepare(options, {"torch-raw": ckpt})
        output = source.parent / "out"
        generation.generate_audio(
            options["output_path"], "torch-raw", output, device="cpu"
        )
        loaded, _checkpoint, _rate = generation.load_torch_generator(ckpt, device="cpu")
        for ordinal, row in enumerate(rows):
            np.testing.assert_array_equal(
                _read_wav(output / f"{row['id']}.wav"),
                _direct_infer(loaded, row, 42 + ordinal),
            )

    @pytest.mark.parametrize("mode", ["none", "capacity"])
    def test_eval_legacy_report_schema_unchanged(
        self, ref_eval_inputs, monkeypatch, mode
    ):
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(_tiny_vits(monkeypatch, mode), source.parent / "m.ckpt")
        _prepare(options, {"torch-raw": ckpt})
        report = generation.generate_audio(
            options["output_path"], "torch-raw", source.parent / "out", device="cpu"
        )
        assert set(report) == LEGACY_REPORT_KEYS
        assert all(set(clip) == LEGACY_CLIP_KEYS for clip in report["clips"])

    @pytest.mark.parametrize("mode", ["none", "capacity"])
    def test_eval_legacy_model_ignores_manifest_reference_spec(
        self, ref_eval_inputs, monkeypatch, mode
    ):
        # 参照 spec の来歴付き manifest でも旧モデルの WAV は変わらない
        from piper_train.tools import generate_eval_audio as generation

        source, rows, options = ref_eval_inputs
        ckpt = _save_checkpoint(_tiny_vits(monkeypatch, mode), source.parent / "m.ckpt")
        wavs = {}
        for label, settings in (("legacy", None), ("spec", _reference_defaults())):
            _prepare(options, {"torch-raw": ckpt}, reference_spec=settings)
            output = source.parent / label
            generation.generate_audio(
                options["output_path"], "torch-raw", output, device="cpu"
            )
            wavs[label] = [_read_wav(output / f"{row['id']}.wav") for row in rows]
        for legacy, spec in zip(wavs["legacy"], wavs["spec"], strict=True):
            np.testing.assert_array_equal(legacy, spec)


@pytest.mark.unit
@pytest.mark.usefixtures("frontend_deps")
class TestReferenceSpecOnnxEval:
    """ONNX backend: 契約の入力名 (reference_spec / reference_spec_lengths) への feed。

    Task 8R の export と merge した後は、実 export の ref_spec ONNX でも
    ``test_eval_feeds_reference_spec_for_ref_spec_model`` 相当を再実行すること。
    """

    def test_eval_onnx_feeds_reference_spec_contract_inputs(self, ref_eval_inputs):
        from piper_train.tools import generate_eval_audio as generation

        source, rows, options = ref_eval_inputs
        onnx_path = _echo_onnx(source.parent / "echo.onnx")
        _prepare(options, {"onnx": onnx_path}, reference_spec=_reference_defaults())
        output = source.parent / "out"
        generation.generate_audio(options["output_path"], "onnx", output)
        for row in rows:
            spec = _frontend(source.parent / row["reference_audio_paths"][0])
            echoed = _read_wav(output / f"{row['id']}.wav")
            # float32 のまま往復するので bit 一致 (lengths は小さい整数で厳密)
            assert echoed[0] == spec.shape[-1]
            np.testing.assert_array_equal(echoed[1:], spec.numpy().reshape(-1))

    def test_eval_onnx_ref_spec_requires_lengths_input(self, ref_eval_inputs):
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        onnx_path = _echo_onnx(source.parent / "echo.onnx", with_lengths=False)
        _prepare(options, {"onnx": onnx_path}, reference_spec=_reference_defaults())
        output = source.parent / "out"
        with pytest.raises(ValueError, match="reference_spec_lengths"):
            generation.generate_audio(options["output_path"], "onnx", output)
        assert not (output / "generation.json").exists()

    def test_eval_onnx_ref_spec_requires_manifest_reference_spec(
        self, ref_eval_inputs
    ):
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        onnx_path = _echo_onnx(source.parent / "echo.onnx")
        _prepare(options, {"onnx": onnx_path})
        output = source.parent / "out"
        with pytest.raises(ValueError, match="--reference-spec"):
            generation.generate_audio(options["output_path"], "onnx", output)
        assert not (output / "generation.json").exists()

    def test_eval_onnx_ref_spec_requires_reference_audio(self, ref_eval_inputs):
        from piper_train.tools import generate_eval_audio as generation

        source, rows, options = ref_eval_inputs
        onnx_path = _echo_onnx(source.parent / "echo.onnx")
        rows[0]["reference_audio_paths"] = []
        _write_rows(source, rows)
        _prepare(options, {"onnx": onnx_path})
        output = source.parent / "out"
        with pytest.raises(ValueError, match="reference audio"):
            generation.generate_audio(options["output_path"], "onnx", output)
        assert not (output / "generation.json").exists()

    def test_eval_onnx_ref_spec_rejects_channel_mismatch(self, ref_eval_inputs):
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        onnx_path = _echo_onnx(source.parent / "echo.onnx", spec_channels=257)
        _prepare(options, {"onnx": onnx_path}, reference_spec=_reference_defaults())
        output = source.parent / "out"
        with pytest.raises(ValueError, match="filter_length"):
            generation.generate_audio(options["output_path"], "onnx", output)
        assert not (output / "generation.json").exists()

    def test_eval_legacy_onnx_feeds_only_legacy_inputs(self, ref_eval_inputs):
        # 旧 ONNX は来歴付き manifest でも旧入力だけを受け取り、report も旧 schema
        from piper_train.tools import generate_eval_audio as generation

        source, _rows, options = ref_eval_inputs
        onnx_path = _legacy_onnx(source.parent / "legacy.onnx")
        _prepare(options, {"onnx": onnx_path}, reference_spec=_reference_defaults())
        report = generation.generate_audio(
            options["output_path"], "onnx", source.parent / "out"
        )
        assert set(report) == LEGACY_REPORT_KEYS
        assert all(set(clip) == LEGACY_CLIP_KEYS for clip in report["clips"])
