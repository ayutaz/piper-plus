"""Usage notice for models with terms (docs/reference/model-resolution.md §9)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


sys.path.insert(0, str(Path(__file__).parent.parent))

from piper_plus import download  # noqa: E402
from piper_plus.download import (  # noqa: E402
    MODEL_NOTICE_FOOTER,
    PIPER_PLUS_VOICES,
    get_model_notice,
    is_model_notice_disabled,
    print_model_notice,
    show_model_notice,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "test" / "model_resolution_vectors.json"
TSUKUYOMI = "ja_JP-tsukuyomi-chan-medium"
NOTICE = PIPER_PLUS_VOICES[TSUKUYOMI]["notice"]


@pytest.fixture(autouse=True)
def _fresh_notice_state(monkeypatch):
    monkeypatch.setattr(download, "_shown_model_notices", set())
    monkeypatch.delenv("PIPER_PLUS_DISABLE_MODEL_NOTICE", raising=False)


def test_catalog_notice_matches_canonical():
    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))["voice_catalog"]
    assert canonical[TSUKUYOMI]["notice"] == NOTICE
    assert (
        PIPER_PLUS_VOICES[TSUKUYOMI]["notice_files"]
        == canonical[TSUKUYOMI]["notice_files"]
    )


@pytest.mark.parametrize(
    "value",
    [
        TSUKUYOMI,
        "tsukuyomi",
        "tsukuyomi-chan",
        "ja-tsukuyomi",
        "ayousanz/piper-plus-tsukuyomi-chan",
        "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/"
        "tsukuyomi-chan-6lang-fp16.onnx",
        "/models/tsukuyomi-chan-6lang-fp16.onnx",
        r"C:\Users\me\models\tsukuyomi-chan-6lang-fp16.onnx",
        "releases/zs-v1/tsukuyomi.onnx",
        Path("cache") / "ayousanz--piper-plus-tsukuyomi-chan" / "tsukuyomi.onnx",
    ],
)
def test_tsukuyomi_inputs_get_the_notice(value):
    assert get_model_notice(value) == NOTICE


@pytest.mark.parametrize(
    "value",
    [
        "css10",
        "ja_JP-css10-6lang-medium",
        "base",
        "ayousanz/piper-plus-base",
        "/models/css10-ja-6lang-fp16.onnx",
        "/models/my-tsukuyomi-like.onnx",
        "tsukuyomi.onnx.json",
        "",
        None,
    ],
)
def test_other_inputs_get_no_notice(value):
    assert get_model_notice(value) is None


def test_first_matching_candidate_wins():
    assert get_model_notice("does-not-exist", None, "tsukuyomi") == NOTICE


@pytest.mark.parametrize(
    ("value", "disabled"),
    [
        ("1", True),
        (" TRUE ", True),
        ("yes", True),
        ("0", False),
        ("", False),
        ("no", False),
    ],
)
def test_disable_value_parsing(value, disabled):
    assert is_model_notice_disabled(value) is disabled


def test_print_once_per_process():
    out = io.StringIO()
    assert print_model_notice("tsukuyomi", stream=out) is True
    assert print_model_notice("tsukuyomi-chan", stream=out) is False
    lines = out.getvalue().splitlines()
    assert lines == [*NOTICE, MODEL_NOTICE_FOOTER]


def test_env_var_disables(monkeypatch):
    monkeypatch.setenv("PIPER_PLUS_DISABLE_MODEL_NOTICE", "true")
    out = io.StringIO()
    assert print_model_notice("tsukuyomi", stream=out) is False
    assert out.getvalue() == ""


def test_show_model_notice_ignores_none():
    out = io.StringIO()
    assert show_model_notice(None, stream=out) is False
    assert out.getvalue() == ""


def test_print_goes_to_stderr_by_default(capsys):
    print_model_notice("tsukuyomi")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert NOTICE[1] in captured.err


# --- executables ---------------------------------------------------------


class _LoadReached(Exception):
    pass


def _run_main_until_load(module, argv: list[str]) -> None:
    with (
        patch.object(sys, "argv", argv),
        patch.object(module, "ensure_voice_exists"),
        patch.object(module.PiperVoice, "load", side_effect=_LoadReached),
        pytest.raises(_LoadReached),
    ):
        module.main()


def _place_tsukuyomi(tmp_path: Path) -> Path:
    onnx = tmp_path / "tsukuyomi-chan-6lang-fp16.onnx"
    onnx.write_bytes(b"")
    (tmp_path / "config.json").write_bytes(b"")
    return onnx


@pytest.mark.parametrize("module_name", ["__main__", "http_server"])
def test_executables_print_notice_for_alias(tmp_path, capsys, module_name):
    import importlib

    module = importlib.import_module(f"piper_plus.{module_name}")
    _place_tsukuyomi(tmp_path)
    _run_main_until_load(
        module, ["piper-plus", "--model", "tsukuyomi", "--data-dir", str(tmp_path)]
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count(NOTICE[0]) == 1
    assert MODEL_NOTICE_FOOTER in captured.err


def test_cli_prints_notice_for_path(tmp_path, capsys):
    from piper_plus import __main__ as cli

    onnx = _place_tsukuyomi(tmp_path)
    _run_main_until_load(cli, ["piper-plus", "--model", str(onnx)])
    assert NOTICE[2] in capsys.readouterr().err


def test_cli_notice_disabled_by_env(tmp_path, capsys, monkeypatch):
    from piper_plus import __main__ as cli

    monkeypatch.setenv("PIPER_PLUS_DISABLE_MODEL_NOTICE", "1")
    onnx = _place_tsukuyomi(tmp_path)
    _run_main_until_load(cli, ["piper-plus", "--model", str(onnx)])
    assert NOTICE[0] not in capsys.readouterr().err


def test_cli_no_notice_for_other_model(tmp_path, capsys):
    from piper_plus import __main__ as cli

    onnx = tmp_path / "css10-ja-6lang-fp16.onnx"
    onnx.write_bytes(b"")
    _run_main_until_load(cli, ["piper-plus", "--model", str(onnx)])
    assert NOTICE[0] not in capsys.readouterr().err


def test_download_model_prints_notice(tmp_path, capsys):
    from piper_plus import __main__ as cli

    onnx = _place_tsukuyomi(tmp_path)
    argv = [
        "piper-plus",
        "--download-model",
        "tsukuyomi",
        "--download-dir",
        str(tmp_path),
    ]
    with (
        patch.object(sys, "argv", argv),
        patch.object(download, "download_model", return_value=(onnx, onnx)),
        pytest.raises(SystemExit) as exc,
    ):
        cli.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert NOTICE[0] in captured.err


# --- high-level API ---------------------------------------------------------


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.get_inputs.return_value = []
    session.get_providers.return_value = ["CPUExecutionProvider"]
    return session


@pytest.mark.parametrize(
    ("model", "file_name", "expected"),
    [
        ("tsukuyomi", "tsukuyomi-chan-6lang-fp16.onnx", NOTICE),
        (
            "ayousanz/piper-plus-tsukuyomi-chan",
            "tsukuyomi-chan-6lang-fp16.onnx",
            NOTICE,
        ),
        ("css10", "css10-ja-6lang-fp16.onnx", None),
    ],
)
def test_piper_plus_exposes_notice_without_printing(
    tmp_path, capsys, model, file_name, expected
):
    from piper_plus.api.api import PiperPlus

    onnx = tmp_path / file_name
    config = tmp_path / "config.json"
    with (
        patch("piper_plus.api.api.resolve_model", return_value=(onnx, config)),
        patch(
            "piper_plus.api.api.load_config",
            return_value={"phoneme_id_map": {}, "audio": {"sample_rate": 22050}},
        ),
        patch("piper_plus.api.api.create_ort_session", return_value=_mock_session()),
        patch("piper_plus.api.api.warmup_session"),
    ):
        tts = PiperPlus(model, device="cpu")
    assert tts.model_notice == expected
    assert capsys.readouterr().err.count(NOTICE[0]) == 0
