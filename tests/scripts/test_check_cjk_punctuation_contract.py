"""Tests for scripts/build_cjk_punctuation_fixture.py and
scripts/check_cjk_punctuation_contract.py (Issue #823)."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_cjk_punctuation_fixture as fixture  # noqa: E402
import check_cjk_punctuation_contract as gate  # noqa: E402


def _contract(**neutral_overrides) -> dict:
    contract = tomllib.loads(fixture.CONTRACT.read_text(encoding="utf-8"))
    contract["neutral"].update(neutral_overrides)
    return contract


def test_repository_fixture_is_up_to_date() -> None:
    assert fixture.main(["--check"]) == 0


def test_repository_consumers_read_the_fixture() -> None:
    assert gate.consumer_problems(_contract()) == []


def test_every_runtime_has_a_consumer_test() -> None:
    tests = _contract()["consumers"]["tests"]
    for prefix in (
        "src/python/g2p/",
        "src/python_run/",
        "src/rust/",
        "src/go/",
        "src/wasm/",
        "src/csharp/",
        "src/cpp/",
    ):
        assert any(t.startswith(prefix) for t in tests), prefix


@pytest.mark.parametrize(
    ("cp", "latin"),
    [
        (0xFF0C, ","),  # ， fullwidth ASCII
        (0xFF10, "0"),  # ０
        (0xFF5E, "~"),  # ～ (last fullwidth ASCII)
        (0x3001, ","),  # 、
        (0x3002, "."),  # 。
        (0xFF61, "."),  # ｡
        (0xFF64, ","),  # ､
        (0x300C, " "),  # 「
        (0x3000, " "),  # ideographic space
        (0xFF5F, " "),  # ｟ (past the fullwidth ASCII block)
        (0xFFE5, " "),  # ￥
    ],
)
def test_latin_replacement(cp: int, latin: str) -> None:
    assert fixture.latin_replacement(cp, _contract()) == latin


def test_fullwidth_latin_letters_are_never_neutral() -> None:
    codes = set(fixture.neutral_code_points(_contract()))
    assert not codes & {*range(0xFF21, 0xFF3B), *range(0xFF41, 0xFF5B)}


def test_neutral_range_over_fullwidth_letters_is_rejected(monkeypatch, tmp_path: Path) -> None:
    contract = fixture.CONTRACT.read_text(encoding="utf-8").replace(
        '["U+FF00", "U+FF20"]', '["U+FF00", "U+FF21"]'
    )
    path = tmp_path / "contract.toml"
    path.write_text(contract, encoding="utf-8")
    monkeypatch.setattr(fixture, "CONTRACT", path)
    with pytest.raises(ValueError, match="fullwidth Latin"):
        fixture.build()


def test_stale_fixture_fails_the_check(monkeypatch, tmp_path: Path) -> None:
    out = tmp_path / "cases.json"
    out.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(fixture, "OUTPUT", out)
    monkeypatch.setattr(fixture, "REPO_ROOT", tmp_path)
    assert fixture.main(["--check"]) == 1


def test_missing_consumer_is_reported(tmp_path: Path) -> None:
    contract = {"consumers": {"tests": ["src/x/test_a.py"]}}
    assert gate.consumer_problems(contract, tmp_path) == [
        "src/x/test_a.py: listed in [consumers].tests but does not exist"
    ]


def test_consumer_that_stopped_reading_the_fixture_is_reported(tmp_path: Path) -> None:
    (tmp_path / "test_a.py").write_text("assert True\n", encoding="utf-8")
    contract = {"consumers": {"tests": ["test_a.py"]}}
    assert gate.consumer_problems(contract, tmp_path) == [
        "test_a.py: does not read cjk_punctuation_cases.json"
    ]


def test_empty_consumer_list_is_reported(tmp_path: Path) -> None:
    assert gate.consumer_problems({}, tmp_path) == ["[consumers].tests is empty"]
