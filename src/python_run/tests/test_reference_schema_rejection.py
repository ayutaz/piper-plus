"""参照spec入力 (ref_spec_v1) を宣言した ONNX を Python runtime が読み込み時に拒否する。

ref_spec_v1 の ONNX は ``reference_spec`` [B, 513, T_ref] float32 と
``reference_spec_lengths`` [B] int64 を必須入力に持つ。Python runtime
(``PiperVoice`` / ``piper_plus.api`` engine / HTTP server) はこの入力を
組み立てられないため、読み込み時 (warmup・合成より前) に、参照spectrogram入力が
必要でこの runtime は未対応であることとモデルの path を含む明示エラーで止める。
旧モデル (legacy) は従来どおり読み込め、出力も変わらない。

モデルは ``src/cpp/tests/fixtures/reference_spec_inputs/`` の tiny ONNX
(``generate.py`` の出力、C++ test と共用) を tmp_path に複製して使う。
複製するのは ORT の ``.opt.onnx`` cache を repo 内に書かないため。
onnxruntime だけで動くので onnx/torch の無い CI (Windows) でも実行される。
生成 script と commit 済みファイルの一致は末尾の drift test で検査する。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import onnxruntime
import pytest

from piper_plus import voice as voice_module
from piper_plus.api.engine import create_ort_session, synthesize
from piper_plus.config import PiperConfig
from piper_plus.util import audio_float_to_int16
from piper_plus.voice import PiperVoice


FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "cpp"
    / "tests"
    / "fixtures"
    / "reference_spec_inputs"
)
FIXTURE_NAMES = (
    "legacy_minimal",
    "legacy_full",
    "ref_spec",
    "ref_spec_without_lengths",
    "ref_spec_lengths_only",
)
# generate.py の WAVE_GAIN と同値 (drift test で一致を検査)。
WAVE_GAIN = np.float32(0.001)

# 現行 zero-shot export (zs-v1) と同じ入力の並び。
LEGACY_FULL_INPUTS = [
    "input",
    "input_lengths",
    "scales",
    "speaker_embedding",
    "lid",
    "prosody_features",
]

# MIN_PHONEME_IDS (15) 以上: Strategy A の padding/trim が入らない長さ。
# 出力が graph の式だけで決まり、期待値を独立に計算できる。
UNPADDED_IDS = [1] + [4 + (i % 26) for i in range(20)] + [2]


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    for name in FIXTURE_NAMES:
        shutil.copyfile(FIXTURE_DIR / f"{name}.onnx", tmp_path / f"{name}.onnx")
    shutil.copyfile(FIXTURE_DIR / "config.json", tmp_path / "config.json")
    return tmp_path


def _load_voice(model_dir: Path, name: str) -> PiperVoice:
    return PiperVoice.load(
        model_dir / f"{name}.onnx", config_path=model_dir / "config.json"
    )


def _cpu_session(path: Path) -> onnxruntime.InferenceSession:
    return onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _fixture_config() -> PiperConfig:
    return PiperConfig.from_dict(
        json.loads((FIXTURE_DIR / "config.json").read_text(encoding="utf-8"))
    )


# ---------------------------------------------------------------------------
# PiperVoice.load (CLI / HTTP server / webui の読み込み経路)
# ---------------------------------------------------------------------------


def test_python_runtime_rejects_reference_spec_model(model_dir: Path) -> None:
    from piper_plus.model_inputs import UnsupportedModelInputError

    with pytest.raises(UnsupportedModelInputError):
        _load_voice(model_dir, "ref_spec")


def test_rejection_error_is_runtime_error(model_dir: Path) -> None:
    # 既存の呼び出し側が RuntimeError で受けられること (専用型は RuntimeError 派生)。
    with pytest.raises(RuntimeError):
        _load_voice(model_dir, "ref_spec")


def test_rejection_message_says_reference_spectrogram_unsupported(
    model_dir: Path,
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        _load_voice(model_dir, "ref_spec")
    message = str(excinfo.value)
    assert "reference-spectrogram input" in message
    assert "does not support" in message


# message の括弧内は「model が宣言した参照入力だけ」を固定順で並べる。
# "reference_spec" は "reference_spec_lengths" の部分文字列なので、区切り
# (",", ";") まで含めて照合し、片方だけ宣言した model で余計な名前が
# 出ないことも確かめる (C++ test と同じ基準)。
DECLARED_REFERENCE_INPUTS = {
    "ref_spec": "(reference_spec, reference_spec_lengths;",
    "ref_spec_without_lengths": "(reference_spec;",
    "ref_spec_lengths_only": "(reference_spec_lengths;",
}


@pytest.mark.parametrize("name", sorted(DECLARED_REFERENCE_INPUTS))
def test_rejection_message_lists_exactly_the_declared_inputs(
    model_dir: Path, name: str
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        _load_voice(model_dir, name)
    assert DECLARED_REFERENCE_INPUTS[name] in str(excinfo.value)


def test_rejection_message_includes_model_path(model_dir: Path) -> None:
    model_path = model_dir / "ref_spec.onnx"
    with pytest.raises(RuntimeError) as excinfo:
        PiperVoice.load(model_path, config_path=model_dir / "config.json")
    assert str(model_path) in str(excinfo.value)


def _warmup_failure_records(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if "Warmup failed" in r.getMessage()]


def test_rejection_happens_before_warmup(
    model_dir: Path, caplog: pytest.LogCaptureFixture, monkeypatch
) -> None:
    # warmup が走ると必須入力欠落で ORT run が失敗し、"Warmup failed" を warning
    # に残して握り潰す。読み込み時の拒否は warmup (ORT run) より前に起きる。
    monkeypatch.delenv("PIPER_PLUS_DISABLE_WARMUP", raising=False)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            _load_voice(model_dir, "ref_spec")
    assert not _warmup_failure_records(caplog)


def test_rejection_happens_before_warmup_on_inline_path(
    model_dir: Path, caplog: pytest.LogCaptureFixture, monkeypatch
) -> None:
    # piper_train の無い配布環境の inline 経路 (_warmup_session) でも同じ順序。
    monkeypatch.delenv("PIPER_PLUS_DISABLE_WARMUP", raising=False)
    monkeypatch.setattr(voice_module, "_HAS_SHARED_ORT_UTILS", False)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            _load_voice(model_dir, "ref_spec")
    assert not _warmup_failure_records(caplog)


def test_rejects_on_standalone_inline_session_path(
    model_dir: Path, monkeypatch
) -> None:
    # piper_train が無い配布環境 (PyPI wheel 単体) の inline session 経路。
    monkeypatch.setattr(voice_module, "_HAS_SHARED_ORT_UTILS", False)
    with pytest.raises(RuntimeError, match="reference-spectrogram input"):
        _load_voice(model_dir, "ref_spec")


def test_python_runtime_legacy_model_loads(model_dir: Path) -> None:
    voice = _load_voice(model_dir, "legacy_full")
    assert [i.name for i in voice.session.get_inputs()] == LEGACY_FULL_INPUTS


def test_python_runtime_legacy_minimal_model_loads(model_dir: Path) -> None:
    voice = _load_voice(model_dir, "legacy_minimal")
    assert [i.name for i in voice.session.get_inputs()] == [
        "input",
        "input_lengths",
        "scales",
    ]


def test_python_runtime_legacy_inline_path_loads(model_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(voice_module, "_HAS_SHARED_ORT_UTILS", False)
    voice = _load_voice(model_dir, "legacy_full")
    assert [i.name for i in voice.session.get_inputs()] == LEGACY_FULL_INPUTS


def test_python_runtime_legacy_synthesis_is_unchanged(model_dir: Path) -> None:
    voice = _load_voice(model_dir, "legacy_full")
    audio = np.frombuffer(voice.synthesize_ids_to_raw(UNPADDED_IDS), dtype=np.int16)
    # graph は output = float32(id) * float32(0.001) (他入力は ×0 で加算)。
    # 同じ IEEE float32 演算を numpy で再現し、runtime 側の後処理
    # (audio_float_to_int16) を通した値と bit 一致を要求する (許容誤差 0)。
    expected = audio_float_to_int16(
        np.array(UNPADDED_IDS, dtype=np.float32) * WAVE_GAIN
    )
    np.testing.assert_array_equal(audio, expected)


# ---------------------------------------------------------------------------
# piper_plus.api engine (PiperPlus 高レベル API / Wyoming adapter の読み込み経路)
# ---------------------------------------------------------------------------


def test_http_engine_rejects_reference_spec_model(model_dir: Path) -> None:
    from piper_plus.model_inputs import UnsupportedModelInputError

    with pytest.raises(UnsupportedModelInputError):
        create_ort_session(model_dir / "ref_spec.onnx", device="cpu")


def test_http_engine_rejection_message_includes_model_path(model_dir: Path) -> None:
    model_path = model_dir / "ref_spec.onnx"
    with pytest.raises(RuntimeError) as excinfo:
        create_ort_session(model_path, device="cpu")
    assert str(model_path) in str(excinfo.value)


def test_http_engine_rejects_reference_spec_lengths_only_model(
    model_dir: Path,
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        create_ort_session(model_dir / "ref_spec_lengths_only.onnx", device="cpu")
    assert DECLARED_REFERENCE_INPUTS["ref_spec_lengths_only"] in str(excinfo.value)


def test_http_engine_legacy_model_loads(model_dir: Path) -> None:
    session = create_ort_session(model_dir / "legacy_full.onnx", device="cpu")
    assert [i.name for i in session.get_inputs()] == LEGACY_FULL_INPUTS


def test_http_engine_legacy_synthesis_is_unchanged(model_dir: Path) -> None:
    # legacy_minimal を使う: engine の _fill_speaker_embedding_inputs は mask を
    # 宣言しない speaker_embedding モデル (zs-v1 の並び) にも mask を送り ORT が
    # "Invalid input name" で落ちる既存挙動があり、本 task の範囲外のため。
    session = create_ort_session(model_dir / "legacy_minimal.onnx", device="cpu")
    audio = synthesize(session, UNPADDED_IDS)
    # engine.audio_float_to_int16 は clip × 32767 (正規化なし)。同じ float32 演算で
    # 期待値を作り bit 一致を要求する (許容誤差 0)。
    wave = np.array(UNPADDED_IDS, dtype=np.float32) * WAVE_GAIN
    expected = (np.clip(wave, -1.0, 1.0) * 32767.0).astype(np.int16)
    np.testing.assert_array_equal(audio, expected)


def test_piper_plus_api_rejects_reference_spec_model(model_dir: Path) -> None:
    from piper_plus.api import PiperPlus

    with pytest.raises(RuntimeError, match="reference-spectrogram input"):
        PiperPlus(
            str(model_dir / "ref_spec.onnx"),
            config=str(model_dir / "config.json"),
            device="cpu",
            download=False,
        )


def test_piper_plus_api_legacy_model_loads(model_dir: Path) -> None:
    from piper_plus.api import PiperPlus

    tts = PiperPlus(
        str(model_dir / "legacy_full.onnx"),
        config=str(model_dir / "config.json"),
        device="cpu",
        download=False,
    )
    assert tts.sample_rate == 22050


# ---------------------------------------------------------------------------
# HTTP server (create_app は PiperVoice.load 以外で組んだ voice も受け取る)
# ---------------------------------------------------------------------------


def test_http_server_create_app_rejects_reference_spec_voice(model_dir: Path) -> None:
    pytest.importorskip("fastapi")
    from piper_plus.http_server import create_app

    voice = PiperVoice(
        session=_cpu_session(model_dir / "ref_spec.onnx"), config=_fixture_config()
    )
    with pytest.raises(RuntimeError, match="reference-spectrogram input"):
        create_app(voice, {})


def test_http_server_create_app_message_uses_explicit_model_path(
    model_dir: Path,
) -> None:
    pytest.importorskip("fastapi")
    from piper_plus.http_server import create_app

    model_path = model_dir / "ref_spec.onnx"
    voice = PiperVoice(session=_cpu_session(model_path), config=_fixture_config())
    with pytest.raises(RuntimeError) as excinfo:
        create_app(voice, {}, model_path=model_path)
    assert str(model_path) in str(excinfo.value)


def test_http_server_create_app_without_model_path_uses_placeholder(
    model_dir: Path,
) -> None:
    # path は呼び出し側が明示的に渡す。ORT の private 属性 (session._model_path、
    # cache 経路では .opt.onnx を指しうる) には依存しない。
    pytest.importorskip("fastapi")
    from piper_plus.http_server import create_app

    voice = PiperVoice(
        session=_cpu_session(model_dir / "ref_spec.onnx"), config=_fixture_config()
    )
    with pytest.raises(RuntimeError) as excinfo:
        create_app(voice, {})
    assert "Model (model path not provided) requires" in str(excinfo.value)


def test_http_server_create_app_accepts_legacy_voice_with_model_path(
    model_dir: Path,
) -> None:
    pytest.importorskip("fastapi")
    from piper_plus.http_server import create_app

    model_path = model_dir / "legacy_full.onnx"
    voice = PiperVoice(session=_cpu_session(model_path), config=_fixture_config())
    app = create_app(voice, {}, model_path=model_path)
    assert app.title == "Piper TTS HTTP Server"


def test_http_server_create_app_accepts_legacy_voice(model_dir: Path) -> None:
    pytest.importorskip("fastapi")
    from piper_plus.http_server import create_app

    voice = PiperVoice(
        session=_cpu_session(model_dir / "legacy_full.onnx"),
        config=_fixture_config(),
    )
    app = create_app(voice, {})
    assert app.title == "Piper TTS HTTP Server"


# ---------------------------------------------------------------------------
# reject_reference_spec_inputs (入力名の集合だけを見る判定) の境界
# ---------------------------------------------------------------------------


def test_reference_input_check_accepts_empty_input_list() -> None:
    from piper_plus.model_inputs import reject_reference_spec_inputs

    assert reject_reference_spec_inputs([], "m.onnx") is None


def test_reference_input_check_accepts_legacy_input_names() -> None:
    from piper_plus.model_inputs import reject_reference_spec_inputs

    names = [*LEGACY_FULL_INPUTS, "sid", "speaker_embedding_mask"]
    assert reject_reference_spec_inputs(names, "m.onnx") is None


@pytest.mark.parametrize(
    "near_miss",
    ["reference_spec_x", "reference_specs", "Reference_Spec", "reference_spec "],
)
def test_reference_input_check_matches_exact_names_only(near_miss: str) -> None:
    # 判定は完全一致。似た名前の入力 (将来の別 schema 等) は拒否理由にしない。
    from piper_plus.model_inputs import reject_reference_spec_inputs

    assert reject_reference_spec_inputs(["input", near_miss], "m.onnx") is None


def test_reference_input_check_lists_names_in_fixed_order() -> None:
    # graph 上の宣言順に依らず message は固定順 (C++ と同じ文面になる)。
    from piper_plus.model_inputs import (
        UnsupportedModelInputError,
        reject_reference_spec_inputs,
    )

    with pytest.raises(UnsupportedModelInputError) as excinfo:
        reject_reference_spec_inputs(
            ["reference_spec_lengths", "input", "reference_spec"], "m.onnx"
        )
    assert DECLARED_REFERENCE_INPUTS["ref_spec"] in str(excinfo.value)


def test_reference_input_check_accepts_single_pass_iterable() -> None:
    # session.get_inputs() を generator で渡しても判定できる (1 回だけ走査する)。
    from piper_plus.model_inputs import reject_reference_spec_inputs

    names = iter(["input", "reference_spec_lengths"])
    with pytest.raises(RuntimeError) as excinfo:
        reject_reference_spec_inputs(names, "m.onnx")
    assert DECLARED_REFERENCE_INPUTS["ref_spec_lengths_only"] in str(excinfo.value)


# ---------------------------------------------------------------------------
# commit 済み fixture と generate.py の一致 (C++ test も同じファイルを読む)
# ---------------------------------------------------------------------------


def _load_generator():
    pytest.importorskip("onnx")
    spec = importlib.util.spec_from_file_location(
        "reference_spec_fixture_generator", FIXTURE_DIR / "generate.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_committed_fixture_matches_generator(name: str) -> None:
    import onnx

    generator = _load_generator()
    committed = onnx.load(str(FIXTURE_DIR / f"{name}.onnx"))
    assert committed == generator.build_model(name)


def test_committed_fixture_config_matches_generator() -> None:
    generator = _load_generator()
    committed = (FIXTURE_DIR / "config.json").read_bytes().decode("utf-8")
    assert committed == generator.config_text()


def test_generator_gain_matches_test_expectation() -> None:
    generator = _load_generator()
    assert np.float32(generator.WAVE_GAIN) == WAVE_GAIN
