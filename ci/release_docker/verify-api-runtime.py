import hashlib
import json
import logging
import os
import wave
from pathlib import Path

import numpy as np
from inference import (
    PiperInferenceEngine,
    get_phonemizer,
    text_to_phoneme_ids_and_prosody,
)

from piper_plus_g2p.encode.pua import FIXED_PUA_MAPPING


logging.basicConfig(level=logging.WARNING)
script_sha = hashlib.sha256(Path("/app/inference.py").read_bytes()).hexdigest()
assert script_sha == os.environ["PIPER_EXPECTED_SCRIPT_SHA"]
config = json.loads(Path("/model/published-hf-config.json").read_text())
mapping = config["phoneme_id_map"]
text = "新しいお茶。みんなで飲む時間。"
tokens, prosody = get_phonemizer("ja").phonemize_with_prosody(text)
required = {"sh", "ch", "N_n", "N_uvular"}
assert required <= set(tokens), ("Expected real regression tokens", tokens)
expected = []
expanded_tokens = []
for token in tokens:
    ids = mapping.get(token)
    if ids is None and token in FIXED_PUA_MAPPING:
        ids = mapping.get(chr(FIXED_PUA_MAPPING[token]))
    assert ids is not None, ("Official config does not cover real phoneme", token)
    expected.extend(ids)
    expanded_tokens.extend([token] * len(ids))
ids, aligned_prosody = text_to_phoneme_ids_and_prosody(text, mapping, language="ja")
assert ids == expected
assert len(ids) == len(aligned_prosody)

engine = PiperInferenceEngine(
    "/model/model.onnx", "/model/published-hf-config.json", device="cpu"
)
audio = engine.synthesize(text, language="ja")
assert audio.dtype == np.int16 and len(audio) > 1000 and np.any(audio != 0)
output = Path("/output/corrected-gpu-image-cpu-tsukuyomi.wav")
with wave.open(str(output), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(engine.sample_rate)
    wav.writeframes(audio.astype("<i2").tobytes())
timing = engine.synthesize_with_timing(text, language="ja")
if engine.has_durations:
    assert timing is not None
    assert [entry["phoneme"] for entry in timing["phonemes"]] == expanded_tokens
    assert timing["total_duration_ms"] > 0
    assert all(entry["end_ms"] >= entry["start_ms"] for entry in timing["phonemes"])
    Path("/output/corrected-gpu-image-cpu-phoneme-timing.json").write_text(
        json.dumps(timing, indent=2) + "\n"
    )
else:
    assert timing is None

proof = {
    "scope": "corrected public CUDA-capable Docker image in CPU mode; no GPU allocated; no source overlay",
    "source_revision": os.environ["RELEASE_SOURCE"],
    "image_script_sha256": script_sha,
    "readonly_model": True,
    "network_disabled": True,
    "actual_regression_tokens_preserved": sorted(required),
    "encoded_ids": len(ids),
    "aligned_prosody_entries": len(aligned_prosody),
    "sample_rate": engine.sample_rate,
    "pcm_bits": 16,
    "frames": len(audio),
    "nonzero_samples": int(np.count_nonzero(audio)),
    "wav_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "model_has_durations": engine.has_durations,
    "actual_timing_verified": bool(engine.has_durations),
}
Path("/output/corrected-gpu-image-cpu-runtime-verification.json").write_text(
    json.dumps(proof, indent=2) + "\n"
)
print(json.dumps(proof))
