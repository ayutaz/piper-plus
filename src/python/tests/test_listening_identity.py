"""Blind speaker-identity listening test: trial plan, page build and scoring."""

import json
from pathlib import Path

import numpy as np
import pytest


pytestmark = pytest.mark.unit

CONDITIONS = ("R+", "R-", "Z+", "Z-")


def _wav(path: Path, rate: int, seconds: float = 0.5, amplitude: float = 0.1):
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(rate * seconds)) / rate
    sf.write(path, (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate)
    return path


@pytest.fixture
def pools(tmp_path):
    """Three voices with real references, real cross utterances and synth clips."""
    voices = {}
    for voice in ("ja_a", "ja_b", "tsukuyomi"):
        root = tmp_path / voice
        voices[voice] = {
            "references": [_wav(root / f"ref{i}.wav", 48000) for i in range(2)],
            "real": [_wav(root / f"real{i}.wav", 48000) for i in range(4)],
            "synth": [_wav(root / f"syn{i}.wav", 22050) for i in range(4)],
            "others": [v for v in ("ja_a", "ja_b", "tsukuyomi") if v != voice],
        }
    return voices


def test_plan_has_every_condition_per_voice_and_uses_the_right_pools(pools):
    from piper_train.tools.listening_identity import plan_trials

    trials = plan_trials(pools, per_condition=2, seed=1)
    assert len(trials) == 3 * 4 * 2
    for trial in trials:
        voice = pools[trial["voice"]]
        assert trial["reference"] in voice["references"]
        test = trial["test"]
        if trial["condition"] == "R+":
            assert test in voice["real"]
        elif trial["condition"] == "Z+":
            assert test in voice["synth"]
        elif trial["condition"] == "R-":
            assert any(test in pools[o]["real"] for o in voice["others"])
        else:
            assert any(test in pools[o]["synth"] for o in voice["others"])


def test_plan_is_deterministic_by_seed(pools):
    from piper_train.tools.listening_identity import plan_trials

    assert plan_trials(pools, per_condition=2, seed=7) == plan_trials(
        pools, per_condition=2, seed=7
    )
    assert plan_trials(pools, per_condition=2, seed=7) != plan_trials(
        pools, per_condition=2, seed=8
    )


def test_build_hides_conditions_and_keeps_the_key_outside_the_page(tmp_path, pools):
    import soundfile as sf

    from piper_train.tools.listening_identity import build_session, plan_trials

    trials = plan_trials(pools, per_condition=5, seed=1)
    out = tmp_path / "session"
    key_path = tmp_path / "key.json"
    build_session(trials, out, key_path, session="s1", seed=3, repeat_fraction=0.1)

    page = (out / "index.html").read_text(encoding="utf-8")
    for word in (*CONDITIONS, "ja_a", "tsukuyomi", "syn", "real", "ref0"):
        assert word not in page
    audio = sorted((out / "audio").iterdir())
    assert all(len(p.stem) == 16 for p in audio)
    for path in audio:
        info = sf.info(path)
        assert info.samplerate == 22050
        assert info.subtype == "PCM_16"

    key = json.loads(key_path.read_text(encoding="utf-8"))
    assert key["session"] == "s1"
    repeats = [t for t in key["trials"] if t["repeat_of"] is not None]
    assert len(repeats) == round(0.1 * len(trials))
    assert len(key["trials"]) == len(trials) + len(repeats)
    position = {t["trial"]: i for i, t in enumerate(key["trials"])}
    assert all(position[t["repeat_of"]] < position[t["trial"]] for t in repeats)
    assert not str(key_path.resolve()).startswith(str(out.resolve()))


def test_audio_is_loudness_matched(tmp_path, pools):
    import soundfile as sf

    from piper_train.tools.listening_identity import build_session

    quiet = _wav(tmp_path / "quiet.wav", 22050, amplitude=0.01)
    loud = _wav(tmp_path / "loud.wav", 22050, amplitude=0.5)
    trials = [{"voice": "ja_a", "condition": "Z+", "reference": quiet, "test": loud}]
    out = tmp_path / "session"
    build_session(
        trials, out, tmp_path / "key.json", session="s", seed=0, repeat_fraction=0
    )
    levels = [
        float(np.sqrt(np.mean(sf.read(p)[0] ** 2))) for p in (out / "audio").iterdir()
    ]
    assert levels[0] == pytest.approx(levels[1], rel=0.05)


def _key(conditions):
    trials = []
    for i, (condition, voice) in enumerate(conditions):
        trials.append(
            {
                "trial": f"t{i}",
                "condition": condition,
                "voice": voice,
                "repeat_of": None,
            }
        )
    return {"session": "s1", "trials": trials}


def test_score_counts_identity_answers_per_condition():
    from piper_train.tools.listening_identity import score

    key = _key([("Z+", "ja_a")] * 4 + [("R+", "ja_a")] * 2)
    answers = {
        "session": "s1",
        "answers": {"t0": 4, "t1": 3, "t2": 2, "t3": 1, "t4": 4, "t5": 4},
    }
    result = score([key], [answers])
    assert result["conditions"]["Z+"]["identity_rate"] == pytest.approx(0.5)
    assert result["conditions"]["Z+"]["n"] == 4
    assert result["conditions"]["R+"]["identity_rate"] == pytest.approx(1.0)
    low, high = result["conditions"]["Z+"]["wilson95"]
    assert 0.0 < low < 0.5 < high < 1.0


def test_score_reports_repeat_agreement_and_excludes_repeats_from_rates():
    from piper_train.tools.listening_identity import score

    key = _key([("Z+", "ja_a"), ("R-", "ja_b")])
    key["trials"] += [
        {"trial": "t2", "condition": "Z+", "voice": "ja_a", "repeat_of": "t0"},
        {"trial": "t3", "condition": "R-", "voice": "ja_b", "repeat_of": "t1"},
    ]
    answers = {"session": "s1", "answers": {"t0": 4, "t1": 1, "t2": 3, "t3": 3}}
    result = score([key], [answers])
    assert result["conditions"]["Z+"]["n"] == 1
    assert result["repeat_agreement"] == pytest.approx(0.5)
    assert result["repeat_pairs"] == 2


@pytest.mark.parametrize("problem", ["missing", "out-of-range", "wrong-session"])
def test_score_rejects_incomplete_or_mismatched_answers(problem):
    from piper_train.tools.listening_identity import score

    key = _key([("Z+", "ja_a"), ("R+", "ja_a")])
    answers = {"session": "s1", "answers": {"t0": 4, "t1": 3}}
    if problem == "missing":
        del answers["answers"]["t1"]
    elif problem == "out-of-range":
        answers["answers"]["t1"] = 5
    else:
        answers["session"] = "s2"
    with pytest.raises(ValueError):
        score([key], [answers])
