import hashlib
import json
import wave
from pathlib import Path

import app
import numpy as np


models = app.find_models("/models")
assert "/models/model.onnx" in models
config = app.load_config("/models/model.onnx")
assert config is not None and config["phoneme_id_map"]
rate, audio = app.synthesize(
    "公開した画面の機能で日本語音声を確認します。",
    "/models/model.onnx",
    0,
    "ja",
    0.4,
    1.0,
    0.5,
)
assert rate == 22050 and audio.dtype == np.int16
assert len(audio) > 1000 and np.any(audio != 0)
output = Path("/output/corrected-webui-tsukuyomi.wav")
with wave.open(str(output), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(rate)
    wav.writeframes(audio.astype("<i2").tobytes())
proof = {
    "scope": "public WebUI image: actual model discovery and UI synthesis callback",
    "source_revision": "71acf30c8e23e17b639fd40a8117415c3df55c0a",
    "network_disabled": True,
    "readonly_model": True,
    "sample_rate": rate,
    "frames": len(audio),
    "nonzero_samples": int(np.count_nonzero(audio)),
    "wav_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "ui_source_sha256": hashlib.sha256(Path("/app/app.py").read_bytes()).hexdigest(),
}
Path("/output/webui-runtime-verification.json").write_text(
    json.dumps(proof, indent=2) + "\n"
)
print(json.dumps(proof))
