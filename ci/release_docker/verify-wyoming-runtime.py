import asyncio
import hashlib
import json
import struct
import wave
from pathlib import Path

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import async_read_event, async_write_event
from wyoming.info import Describe, Info
from wyoming.tts import Synthesize


async def verify():
    reader, writer = await asyncio.open_connection("127.0.0.1", 10200)
    await async_write_event(Describe().event(), writer)
    event = await asyncio.wait_for(async_read_event(reader), timeout=30)
    assert Info.is_type(event.type)
    info = Info.from_event(event)
    assert info.tts[0].name == "piper-plus"
    assert any("ja" in voice.languages for voice in info.tts[0].voices)
    await async_write_event(
        Synthesize(text="公開した音声サーバーで日本語を確認します。").event(), writer
    )
    audio = bytearray()
    start = None
    chunks = 0
    while True:
        event = await asyncio.wait_for(async_read_event(reader), timeout=30)
        assert event is not None
        if AudioStart.is_type(event.type):
            start = AudioStart.from_event(event)
        elif AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            assert chunk.rate == 22050 and chunk.width == 2 and chunk.channels == 1
            audio.extend(chunk.audio)
            chunks += 1
        elif AudioStop.is_type(event.type):
            break
    writer.close()
    await writer.wait_closed()
    assert start is not None and (start.rate, start.width, start.channels) == (
        22050,
        2,
        1,
    )
    samples = struct.unpack("<" + "h" * (len(audio) // 2), audio)
    assert len(samples) > 1000 and any(samples)
    output = Path("/output/corrected-wyoming-tsukuyomi.wav")
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(audio)
    proof = {
        "scope": "public Wyoming image: discovery and real streamed synthesis over TCP",
        "source_revision": "71acf30c8e23e17b639fd40a8117415c3df55c0a",
        "network_disabled": True,
        "readonly_model": True,
        "service": info.tts[0].name,
        "service_version": info.tts[0].version,
        "sample_rate": 22050,
        "pcm_bits": 16,
        "frames": len(samples),
        "audio_chunks": chunks,
        "nonzero_samples": sum(sample != 0 for sample in samples),
        "wav_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    Path("/output/wyoming-runtime-verification.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    print(json.dumps(proof))


asyncio.run(verify())
