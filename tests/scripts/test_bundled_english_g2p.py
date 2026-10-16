"""Frozen pre-migration outputs, including OOV and homograph pronunciation."""

import builtins
import json
from dataclasses import asdict
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parents[1] / "fixtures" / "english_g2p_compat.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["text"] or "empty")
def test_bundled_english_preserves_pronunciation(case, monkeypatch):
    original_import = builtins.__import__

    def reject_external(name, *args, **kwargs):
        level = kwargs.get("level", args[3] if len(args) > 3 else 0)
        if level == 0 and name.split(".")[0] in {"g2p_en", "distance"}:
            raise AssertionError(f"External GPL dependency path used: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_external)
    from piper_plus._vendor.g2p_en import G2p as RuntimeG2p
    from piper_plus.phonemize.english import phonemize_english
    from piper_plus_g2p._vendor.g2p_en import G2p
    from piper_plus_g2p.english import phonemize_english_with_prosody

    assert G2p()(case["text"]) == case["arpabet"]
    assert RuntimeG2p()(case["text"]) == case["arpabet"]
    ipa, prosody = phonemize_english_with_prosody(case["text"])
    assert ipa == case["ipa"]
    assert [asdict(p) if p else None for p in prosody] == case["prosody"]
    assert phonemize_english(case["text"]) == case["runtime"]
