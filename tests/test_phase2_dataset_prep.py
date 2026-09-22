"""
Unit and integration tests for Phase 2 Hindi + English dataset preparation.
Verifies:
  1. 202-symbol inventory and SHA256 frozen contract
  2. Hindi G2P phoneme spot checks (t̪ vs ʈ, ɽ, q_uvular)
  3. Padded phoneme_ids (BOS=1, EOS=2, Pad=0) and prosody zip invariant
  4. Hindi text normalization (NFC, ZWJ/ZWNJ stripping, danda preservation)
  5. End-to-end dataset preparation pipeline on mock audio
"""

import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from piper_plus_g2p import get_phonemizer
from piper_plus_g2p.encode.encoder import PiperEncoder
from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_train.tools.prepare_hindi_english_dataset import (
    EXPECTED_SHA256,
    EXPECTED_SYMBOLS,
    LANGUAGE_ID_MAP,
    normalize_text,
    verify_inventory,
)


class TestPhase2DatasetPrep(unittest.TestCase):

    def setUp(self):
        self.id_map = get_phoneme_id_map("hi")
        self.encoder = PiperEncoder(self.id_map, strict=False)
        self.hi_phonemizer = get_phonemizer("hi")
        self.en_phonemizer = get_phonemizer("en")

    def test_inventory_and_hash(self):
        """Verify 202 symbols and exact SHA256 contract."""
        self.assertEqual(len(self.id_map), EXPECTED_SYMBOLS)
        # Must pass without exception
        verify_inventory(self.id_map)

    def test_hindi_g2p_spot_checks(self):
        """Spot check Hindi phonemization: dental vs retroflex, flap ɽ, uvular q."""
        # 1. Dental त vs Retroflex ट
        tal_tokens = self.hi_phonemizer.phonemize("ताल")
        self.assertEqual(tal_tokens[0], "t̪")
        tal_ids = self.encoder.encode(tal_tokens)
        self.assertIn(188, tal_ids)  # t̪ mapped to PUA id 188

        taal_tokens = self.hi_phonemizer.phonemize("टाल")
        self.assertEqual(taal_tokens[0], "ʈ")
        taal_ids = self.encoder.encode(taal_tokens)
        self.assertIn(170, taal_ids)

        # 2. Flap ɽ (id 185)
        bada_tokens = self.hi_phonemizer.phonemize("बड़ा")
        self.assertIn("ɽ", bada_tokens)
        bada_ids = self.encoder.encode(bada_tokens)
        self.assertIn(185, bada_ids)

        # 3. Uvular q (id 201)
        qalam_tokens = self.hi_phonemizer.phonemize("क़लम")
        self.assertIn("q_uvular", qalam_tokens)
        qalam_ids = self.encoder.encode(qalam_tokens)
        self.assertIn(201, qalam_ids)

    def test_padded_ids_and_prosody_alignment(self):
        """Verify BOS=1, EOS=2, Pad=0, and len(phoneme_ids) == len(prosody_features)."""
        text = "नमस्ते दुनिया"
        tokens, prosody = self.hi_phonemizer.phonemize_with_prosody(text)
        p_ids, p_prosody = self.encoder.encode_with_prosody(tokens, prosody)
        prosody_dicts = PiperEncoder.prosody_to_dicts(p_prosody)

        # Invariant 1: exact length match
        self.assertEqual(len(p_ids), len(prosody_dicts))

        # Invariant 2: Starts with BOS (1), pad (0)
        self.assertEqual(p_ids[0], 1)
        self.assertEqual(p_ids[1], 0)

        # Invariant 3: Ends with EOS (2)
        self.assertEqual(p_ids[-1], 2)

        # Invariant 4: Interleaved padding (0) exists
        self.assertIn(0, p_ids)

    def test_text_normalization(self):
        """Verify NFC, ZWJ/ZWNJ stripping, and Devanagari validation."""
        # Non-Devanagari Hindi should be rejected
        self.assertIsNone(normalize_text("Aapka logic sahi hai", "hi"))

        # Devanagari Hindi should pass
        norm = normalize_text("  आपका  लॉजिक  ", "hi")
        self.assertEqual(norm, "आपका  लॉजिक")

        # ZWJ / ZWNJ stripping
        zwj_text = "सं\u200dयुक्त"
        self.assertEqual(normalize_text(zwj_text, "hi"), "संयुक्त")

        # Danda kept
        danda_text = "यह एक वाक्य है। बिल्कुल सही॥"
        self.assertEqual(normalize_text(danda_text, "hi"), danda_text)

    def test_end_to_end_mock_pipeline(self):
        """Run an end-to-end test with synthetic WAV files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hi_dir = tmp_path / "hindi"
            hi_dir.mkdir()
            en_dir = tmp_path / "english"
            en_dir.mkdir()
            out_dir = tmp_path / "output"

            # Create synthetic 1-second 22050Hz sine WAV files
            def create_dummy_wav(path: Path, freq: float = 440.0):
                sr = 22050
                dur = 1.2
                t = np.linspace(0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
                waveform = (0.5 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
                with wave.open(str(path), "w") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sr)
                    wf.writeframes(waveform.tobytes())

            # 2 Hindi utts
            create_dummy_wav(hi_dir / "hi_1.wav", 300)
            create_dummy_wav(hi_dir / "hi_2.wav", 350)
            with open(hi_dir / "metadata.tsv", "w", encoding="utf-8") as f:
                f.write("hi_1.wav\tयह एक बड़ा ताला है।\tspk_01\n")
                f.write("hi_2.wav\tआपका परीक्षण सफल हुआ।\tspk_02\n")

            # 2 English utts (LibriTTS-R format)
            spk_dir = en_dir / "101" / "201"
            spk_dir.mkdir(parents=True)
            create_dummy_wav(spk_dir / "101_201_001.wav", 400)
            create_dummy_wav(spk_dir / "101_201_002.wav", 450)
            with open(spk_dir / "101_201_001.normalized.txt", "w", encoding="utf-8") as f:
                f.write("The test run was successful.")
            with open(spk_dir / "101_201_002.normalized.txt", "w", encoding="utf-8") as f:
                f.write("Asynchronous function completed.")

            # Run main via python subprocess or import
            from piper_train.tools.prepare_hindi_english_dataset import (
                cache_audio_parallel,
                parse_indicvoices_r,
                parse_libritts_r,
                phonemize_dataset,
            )

            cache_dir = out_dir / "cache" / "22050"
            cache_dir.mkdir(parents=True)

            hi_entries = parse_indicvoices_r(hi_dir)
            self.assertEqual(len(hi_entries), 2)
            en_entries = parse_libritts_r(en_dir)
            self.assertEqual(len(en_entries), 2)

            hi_ph, _ = phonemize_dataset(hi_entries, "hi", 0, self.id_map, workers=1)
            en_ph, _ = phonemize_dataset(en_entries, "en", 1, self.id_map, workers=1)
            self.assertEqual(len(hi_ph), 2)
            self.assertEqual(len(en_ph), 2)

            all_wavs = [p["wav_path"] for p in hi_ph + en_ph]
            audio_map = cache_audio_parallel(all_wavs, cache_dir, 22050, workers=1)
            self.assertEqual(len(audio_map), 4)

            # Check files exist
            for norm_p, spec_p, _ in audio_map.values():
                self.assertTrue(Path(norm_p).exists())
                self.assertTrue(Path(spec_p).exists())


if __name__ == "__main__":
    unittest.main()
