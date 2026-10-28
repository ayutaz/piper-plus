"""Blind A/B "which is noisier" test for checking comb_excess against listening."""

import json

import numpy as np
import pytest


pytestmark = pytest.mark.unit


def _wav(path, amplitude=0.1, rate=22050):
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(rate) / rate
    sf.write(path, (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate)
    return path


def _scores(diffs):
    """Two arms with the same stems; arm x is higher by ``diffs[stem]`` dB."""
    return {stem: {"x": 1.0 + diff, "y": 1.0} for stem, diff in diffs.items()}


def test_select_keeps_reverse_pairs_and_limits_each_voice():
    from piper_train.tools.listening_noise_ab import select_pairs

    diffs = {f"ja_a_r0_t{i}": 2.0 for i in range(6)}
    diffs |= {f"ja_b_r0_t{i}": 1.5 for i in range(6)}
    diffs |= {"ja_c_r0_t0": -1.0, "ja_c_r0_t1": 0.3, "ja_c_r0_t2": -0.2}
    pairs = select_pairs(
        _scores(diffs), "x", "y", count=7, min_diff=0.67, max_per_voice=3, seed=1
    )
    stems = [p["stem"] for p in pairs]
    assert len(stems) == 7
    assert "ja_c_r0_t0" in stems  # reverse pair (y noisier by metric) is kept
    assert "ja_c_r0_t1" not in stems and "ja_c_r0_t2" not in stems  # within noise
    for voice in ("ja_a", "ja_b"):
        assert sum(s.startswith(voice + "_") for s in stems) <= 3
    assert (
        select_pairs(
            _scores(diffs), "x", "y", count=7, min_diff=0.67, max_per_voice=3, seed=1
        )
        == pairs
    )


def test_select_fails_when_not_enough_pairs_qualify():
    from piper_train.tools.listening_noise_ab import select_pairs

    with pytest.raises(ValueError):
        select_pairs(
            _scores({"ja_a_r0_t0": 2.0}),
            "x",
            "y",
            count=2,
            min_diff=0.67,
            max_per_voice=3,
            seed=1,
        )


def test_build_hides_arms_and_balances_sides(tmp_path):
    from piper_train.tools.listening_noise_ab import build_session

    pairs = []
    for i in range(10):
        pairs.append(
            {
                "stem": f"ja_a_r0_t{i}",
                "files": {
                    "C0": _wav(tmp_path / "C0" / f"ja_a_r0_t{i}.wav"),
                    "C0-self": _wav(tmp_path / "self" / f"ja_a_r0_t{i}.wav", 0.3),
                },
                "comb": {"C0": 3.0, "C0-self": 1.0},
            }
        )
    out, key_path = tmp_path / "page", tmp_path / "keys" / "noise.json"
    build_session(pairs, out, key_path, session="n1", seed=3, repeats=2)
    page = (out / "index.html").read_text(encoding="utf-8")
    for word in ("C0", "self", "ja_a", "comb"):
        assert word not in page
    key = json.loads(key_path.read_text(encoding="utf-8"))
    originals = [t for t in key["trials"] if t["repeat_of"] is None]
    assert len(originals) == 10 and len(key["trials"]) == 12
    assert {t["higher_comb"] for t in originals} <= {"a", "b"}
    assert 3 <= sum(t["higher_comb"] == "a" for t in originals) <= 7

    import soundfile as sf

    levels = [
        float(np.sqrt(np.mean(sf.read(p)[0] ** 2))) for p in (out / "audio").iterdir()
    ]
    assert max(levels) == pytest.approx(min(levels), rel=0.05)


def test_score_counts_agreement_with_the_higher_comb_side():
    from piper_train.tools.listening_noise_ab import score

    key = {
        "session": "n1",
        "trials": [
            {"trial": "t0", "higher_comb": "a", "repeat_of": None},
            {"trial": "t1", "higher_comb": "b", "repeat_of": None},
            {"trial": "t2", "higher_comb": "a", "repeat_of": None},
            {"trial": "t3", "higher_comb": "b", "repeat_of": None},
            {"trial": "t4", "higher_comb": "a", "repeat_of": "t0"},
        ],
    }
    answers = {
        "session": "n1",
        "answers": {"t0": "a", "t1": "b", "t2": "b", "t3": "b", "t4": "b"},
    }
    result = score(key, answers)
    assert result["n"] == 4
    assert result["agreement"] == pytest.approx(0.75)
    assert result["repeat_agreement"] == pytest.approx(0.0)
    low, high = result["wilson95"]
    assert low < 0.75 < high


@pytest.mark.parametrize("problem", ["missing", "bad-value", "wrong-session"])
def test_score_rejects_bad_answers(problem):
    from piper_train.tools.listening_noise_ab import score

    key = {
        "session": "n1",
        "trials": [{"trial": "t0", "higher_comb": "a", "repeat_of": None}],
    }
    answers = {"session": "n1", "answers": {"t0": "a"}}
    if problem == "missing":
        answers["answers"] = {}
    elif problem == "bad-value":
        answers["answers"]["t0"] = "c"
    else:
        answers["session"] = "n2"
    with pytest.raises(ValueError):
        score(key, answers)
