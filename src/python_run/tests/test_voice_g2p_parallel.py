"""Tests for issue #383 Phase 1 — parallel G2P in PiperVoice.phonemize()."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from piper.voice import (
    _G2P_AUTO_PARALLELISM_CAP,
    _map_sentences,
    _resolve_g2p_parallelism,
)


# ---------------------------------------------------------------------------
# _resolve_g2p_parallelism
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch):
    """Drop PIPER_G2P_PARALLELISM so we exercise the auto path."""
    monkeypatch.delenv("PIPER_G2P_PARALLELISM", raising=False)
    return monkeypatch


def test_resolve_returns_1_for_zero_or_one_sentence(clean_env):
    assert _resolve_g2p_parallelism(0) == 1
    assert _resolve_g2p_parallelism(1) == 1


def test_resolve_auto_parallel_for_multiple_sentences(clean_env):
    n = _resolve_g2p_parallelism(8)
    assert 2 <= n <= _G2P_AUTO_PARALLELISM_CAP
    assert n <= 8


def test_resolve_auto_capped_by_n_sentences(clean_env):
    # With only 2 sentences we must not spawn more than 2 workers even if
    # the host has many cores.
    assert _resolve_g2p_parallelism(2) <= 2


def test_resolve_explicit_1_forces_serial(monkeypatch):
    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "1")
    assert _resolve_g2p_parallelism(10) == 1


def test_resolve_explicit_n_overrides_auto(monkeypatch):
    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "8")
    # capped at n_sentences
    assert _resolve_g2p_parallelism(3) == 3
    assert _resolve_g2p_parallelism(20) == 8


def test_resolve_invalid_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "garbage")
    n = _resolve_g2p_parallelism(8)
    assert n >= 2


# ---------------------------------------------------------------------------
# _map_sentences
# ---------------------------------------------------------------------------


def test_map_sentences_serial_path_zero_sentences():
    assert _map_sentences(lambda x: x.upper(), [], parallelism=4) == []


def test_map_sentences_serial_path_one_sentence_skips_pool():
    """parallelism>=2 but len==1 must not spawn a ThreadPoolExecutor."""
    # Patch concurrent.futures.ThreadPoolExecutor so that it would explode if
    # _map_sentences accidentally instantiated a pool for a single sentence.
    with patch(
        "concurrent.futures.ThreadPoolExecutor",
        side_effect=AssertionError("must not run"),
    ):
        result = _map_sentences(lambda x: x.upper(), ["hello"], parallelism=4)
    assert result == ["HELLO"]


def test_map_sentences_preserves_order():
    sentences = ["a", "b", "c", "d", "e", "f", "g", "h"]
    result = _map_sentences(lambda x: x * 3, sentences, parallelism=4)
    assert result == ["aaa", "bbb", "ccc", "ddd", "eee", "fff", "ggg", "hhh"]


def test_map_sentences_serial_matches_parallel():
    sentences = [f"sentence_{i}" for i in range(20)]

    def fn(s: str) -> tuple[str, int]:
        return (s, len(s))

    serial = _map_sentences(fn, sentences, parallelism=1)
    parallel = _map_sentences(fn, sentences, parallelism=4)
    assert serial == parallel


def test_map_sentences_propagates_exceptions():
    def boom(s: str):
        if s == "fail":
            raise RuntimeError("kaboom")
        return s

    with pytest.raises(RuntimeError, match="kaboom"):
        _map_sentences(boom, ["ok", "fail", "ok2"], parallelism=4)


# ---------------------------------------------------------------------------
# synthesize_stream_raw early-abort behaviour (issue #383 follow-up).
#
# `with ThreadPoolExecutor as pool` defaults to ``wait=True, cancel_futures=False``,
# which would force the consumer's ``break`` to wait until every queued G2P
# finishes. The implementation uses an explicit
# ``shutdown(wait=False, cancel_futures=True)`` so an early break truly cuts
# the rest of the work.
# ---------------------------------------------------------------------------


def test_synthesize_stream_raw_early_break_cancels_queued_g2p(monkeypatch):
    """Consumer-side ``break`` should cancel still-queued G2P submissions.

    We feed many slow sentences and break after the first chunk. The total
    number of G2P calls should be far less than the sentence count (the
    queued futures are cancelled when the generator is abandoned).
    """
    import threading
    import time
    from unittest.mock import MagicMock

    from piper.config import PhonemeType, PiperConfig
    from piper.voice import PiperVoice

    config = PiperConfig(
        num_symbols=100,
        num_speakers=1,
        sample_rate=22050,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
        phoneme_type=PhonemeType.MULTILINGUAL,
    )

    voice = MagicMock(spec=PiperVoice)
    voice.config = config
    voice.session = MagicMock()

    sentences = [f"sentence_{i}." for i in range(50)]
    voice._split_sentences = MagicMock(return_value=sentences)

    g2p_call_count = 0
    g2p_lock = threading.Lock()

    def slow_phonemize(sentence: str) -> list[str]:
        nonlocal g2p_call_count
        with g2p_lock:
            g2p_call_count += 1
        # Simulate a slow G2P backend so the test can break before all
        # queued sentences complete. 50ms × 50 sentences ≈ 2.5s if all
        # ran serially; with parallelism=4 still ~600ms.
        time.sleep(0.05)
        return ["a"]

    voice._phonemize_one_factory = MagicMock(return_value=slow_phonemize)
    voice.phonemes_to_ids = MagicMock(return_value=[1, 10, 2])
    voice._stream_phonemes_to_audio = (
        lambda phonemes_iter, break_b, silence_b, **kw: (
            break_b + b"AUDIO" + break_b + silence_b for _ in phonemes_iter
        )
    )

    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "4")

    gen = PiperVoice.synthesize_stream_raw(voice, "x" * 200)  # bypass short-text
    # Pull just one chunk and abandon.
    first = next(gen)
    assert b"AUDIO" in first
    gen.close()

    # If shutdown waited or cancel_futures was disabled, all 50 sentences
    # would eventually run. With cancel_futures=True we expect well below
    # half (1 returned + max_workers=4 in flight + a few queued before
    # cancel kicks in).
    assert g2p_call_count < len(sentences) // 2, (
        f"Expected most G2P tasks to be cancelled, but {g2p_call_count}/"
        f"{len(sentences)} ran. Did shutdown(wait=False, cancel_futures=True) "
        f"break?"
    )


# ---------------------------------------------------------------------------
# Integration: PiperVoice.phonemize() — serial vs parallel result must match.
# Skipped if the test model / pyopenjtalk-plus are not available.
# ---------------------------------------------------------------------------


_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "test", "models",
    "multilingual-test-medium.onnx",
)


@pytest.mark.skipif(
    not os.path.exists(_MODEL_PATH),
    reason="multilingual-test-medium.onnx not available locally",
)
def test_phonemize_parallel_matches_serial_multilingual(monkeypatch):
    pyopenjtalk = pytest.importorskip("pyopenjtalk")
    del pyopenjtalk  # availability check only
    from piper.voice import PiperVoice

    voice = PiperVoice.load(_MODEL_PATH)

    text = (
        "こんにちは、今日はとても良い天気ですね。"
        "東京駅から新幹線で大阪まで約2時間30分かかります。"
        "昨日の会議では、新しいプロジェクトの方針について話し合いました。"
        "この料理のレシピを教えていただけますか？"
        "桜の花が満開になると、多くの人々が公園でお花見を楽しみます。"
    )

    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "1")
    serial = voice.phonemize(text)

    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "4")
    parallel = voice.phonemize(text)

    assert len(serial) == 5
    assert serial == parallel


@pytest.mark.skipif(
    not os.path.exists(_MODEL_PATH),
    reason="multilingual-test-medium.onnx not available locally",
)
def test_phonemize_concurrent_callers_safe(monkeypatch):
    """Multiple PiperVoice.phonemize() calls from threads must produce the
    same per-thread result as a serial call. Validates that pyopenjtalk-plus
    + the multilingual phonemizer hold up under concurrent access from the
    same process — the actual thread-safety contract Phase 1 relies on.
    """
    pyopenjtalk = pytest.importorskip("pyopenjtalk")
    del pyopenjtalk
    from piper.voice import PiperVoice

    voice = PiperVoice.load(_MODEL_PATH)

    sentences = [
        "こんにちは。",
        "東京駅から新幹線で大阪まで約2時間30分かかります。",
        "昨日の会議では、新しいプロジェクトの方針について話し合いました。",
        "桜の花が満開になると、多くの人々が公園でお花見を楽しみます。",
    ] * 5  # 20 sentences

    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "1")
    expected = [voice.phonemize(s) for s in sentences]

    # Run the same per-sentence calls from a thread pool. Each call processes
    # exactly one sentence (n_sentences == 1) so we exercise concurrent
    # callers, not internal parallelism — which is exactly the regime
    # Phase 1 makes the public phonemize() exposed to.
    monkeypatch.setenv("PIPER_G2P_PARALLELISM", "1")
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(pool.map(voice.phonemize, sentences))

    assert actual == expected
