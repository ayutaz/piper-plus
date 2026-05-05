"""Tests for piper_train.update_model_config — fail-fast on multi-codepoint keys.

This is the L5 (release-pre-flight) test layer for the PUA contract.
See docs/spec/pua-contract.toml.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper_train.update_model_config import (
    UnmappedMultiCodepointKeyError,
    update_phoneme_id_map,
    validate_phoneme_id_map,
)


def _make_config(phoneme_id_map: dict[str, list[int]]) -> dict:
    return {
        "phoneme_type": "multilingual",
        "phoneme_id_map": phoneme_id_map,
        "num_symbols": len(phoneme_id_map),
    }


class TestUpdatePhonemeIdMap:
    """update_phoneme_id_map() should fail fast on unknown multi-codepoint keys."""

    def test_pure_single_codepoint_config_passes(self):
        cfg = _make_config({"a": [0], "i": [1]})
        changed = update_phoneme_id_map(cfg, strict=True)
        assert changed is False
        assert cfg["phoneme_id_map"] == {"a": [0], "i": [1]}

    def test_known_multi_char_token_gets_pua_mapped(self):
        cfg = _make_config({"ch": [0]})  # JA 'ch' -> U+E00E
        update_phoneme_id_map(cfg, strict=True)
        assert "" in cfg["phoneme_id_map"]
        assert "ch" not in cfg["phoneme_id_map"]

    def test_unmapped_multi_codepoint_raises_in_strict_mode(self):
        # PUA v2 registered ɔɪ/œ̃/ɐ̃ already, so use a synthetic unmapped token
        # to verify strict-mode fail-fast behaviour.
        cfg = _make_config({"a": [0], "zz_fake_multi": [1]})
        with pytest.raises(UnmappedMultiCodepointKeyError) as ei:
            update_phoneme_id_map(cfg, strict=True)
        assert "multi-codepoint" in str(ei.value)
        assert "pua.json" in str(ei.value)

    def test_v1_regression_tokens_are_now_mapped_in_strict_mode(self):
        # The exact bug from v1.12.0: ɔɪ/œ̃/ɐ̃ as multi-codepoint keys.
        # With PUA v2 these resolve to single-codepoint PUA characters.
        cfg = _make_config({"a": [0], "ɔɪ": [1], "œ̃": [2], "ɐ̃": [3]})
        update_phoneme_id_map(cfg, strict=True)
        # All keys post-update must be single-codepoint.
        assert all(len(k) == 1 for k in cfg["phoneme_id_map"])

    def test_unmapped_multi_codepoint_warns_in_non_strict(self, capsys):
        cfg = _make_config({"a": [0], "zz_fake_multi": [1]})
        update_phoneme_id_map(cfg, strict=False)
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "zz_fake_multi" in captured.out

    def test_validate_returns_empty_for_clean_config(self):
        cfg = _make_config({"a": [0], "": [1]})  # all single-codepoint
        assert validate_phoneme_id_map(cfg) == []

    def test_validate_returns_multi_codepoint_keys(self):
        cfg = _make_config({"a": [0], "ɔɪ": [1], "œ̃": [2]})
        bad = validate_phoneme_id_map(cfg)
        assert sorted(bad) == sorted(["ɔɪ", "œ̃"])


class TestValidateOnlyEntryPoint:
    """The --validate-only CLI mode should exit non-zero on bad configs."""

    def test_clean_config_exits_zero(self, tmp_path: Path, monkeypatch):
        cfg_path = tmp_path / "clean.json"
        cfg_path.write_text(
            json.dumps(_make_config({"a": [0], "": [1]})),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "sys.argv",
            ["update_model_config", "--validate-only", str(cfg_path)],
        )
        from piper_train.update_model_config import main
        assert main() == 0

    def test_bad_config_exits_nonzero(self, tmp_path: Path, monkeypatch):
        cfg_path = tmp_path / "bad.json"
        cfg_path.write_text(
            json.dumps(_make_config({"a": [0], "ɔɪ": [1]})),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "sys.argv",
            ["update_model_config", "--validate-only", str(cfg_path)],
        )
        from piper_train.update_model_config import main
        assert main() == 1
