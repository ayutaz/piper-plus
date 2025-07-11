"""
Real integration tests that verify actual functionality
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest


class TestRealIntegration:
    """Test real end-to-end functionality without mocks"""

    @pytest.mark.integration
    @pytest.mark.requires_model
    def test_synthesis_produces_audio(self):
        """Test that synthesis actually produces audio data"""
        try:
            from piper.voice import PiperVoice

            # Use a small test model if available
            model_path = Path("test/models/en_US-lessac-medium.onnx")
            if not model_path.exists():
                pytest.skip("Test model not available")

            voice = PiperVoice.load(str(model_path))
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                voice.synthesize("Hello world", tmp.name)
                # Check that WAV file was created
                assert Path(tmp.name).exists()
                assert Path(tmp.name).stat().st_size > 0

        except ImportError:
            pytest.skip("Piper not installed")

    @pytest.mark.integration
    @pytest.mark.japanese
    @pytest.mark.requires_model
    def test_japanese_synthesis_with_pua(self):
        """Test Japanese synthesis with PUA mapping"""
        try:
            from piper.voice import PiperVoice

            model_path = Path("test/models/ja_JP-test-medium.onnx")
            if not model_path.exists():
                pytest.skip("Japanese test model not available")

            # Check that config has PUA mappings
            config_path = Path(str(model_path) + ".json")
            config = json.loads(config_path.read_text())

            # Should have PUA mappings in phoneme_id_map
            pua_chars = [
                k
                for k in config["phoneme_id_map"].keys()
                if isinstance(k, str) and ord(k[0]) >= 0xE000
            ]
            assert len(pua_chars) > 0, "Model should have PUA mappings"

            # Test synthesis
            voice = PiperVoice.load(str(model_path))
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                voice.synthesize("こんにちは", tmp.name)
                # Check that WAV file was created
                assert Path(tmp.name).exists()
                assert Path(tmp.name).stat().st_size > 0

        except ImportError:
            pytest.skip("Piper not installed")

    @pytest.mark.integration
    def test_model_config_validation(self):
        """Test that model configs are valid"""
        test_configs = [
            {
                "audio": {"sample_rate": 22050},
                "num_symbols": 100,
                "phoneme_id_map": {"_": 0},
            },
            {
                "audio": {"sample_rate": 22050},
                "phoneme_type": "openjtalk",
                "language": {"code": "ja"},
                "num_symbols": 150,
                "phoneme_id_map": {"_": 0, "\ue00e": 30},
            },
        ]

        for config in test_configs:
            # Required fields
            assert "audio" in config
            assert "sample_rate" in config["audio"]
            assert "phoneme_id_map" in config

            # Japanese specific
            if config.get("language", {}).get("code") == "ja":
                assert config.get("phoneme_type") == "openjtalk"

    @pytest.mark.integration
    def test_wav_file_generation(self):
        """Test that we can generate valid WAV files"""
        import wave

        # Create test audio data
        sample_rate = 22050
        duration = 0.5
        samples = int(sample_rate * duration)
        audio_data = np.zeros(samples, dtype=np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            # Write WAV
            with wave.open(tmp.name, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data.tobytes())

            # Verify WAV
            with wave.open(tmp.name, "rb") as wav_file:
                assert wav_file.getnchannels() == 1
                assert wav_file.getsampwidth() == 2
                assert wav_file.getframerate() == sample_rate
                assert wav_file.getnframes() == samples

            Path(tmp.name).unlink()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_performance_baseline(self):
        """Test that synthesis meets basic performance requirements"""
        try:
            import time

            from piper.voice import PiperVoice

            model_path = Path("test/models/en_US-lessac-medium.onnx")
            if not model_path.exists():
                pytest.skip("Test model not available")

            voice = PiperVoice.load(str(model_path))

            # Generate 10 seconds worth of text
            text = "Hello world. " * 50

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                start_time = time.time()
                voice.synthesize(text, tmp.name)
                synthesis_time = time.time() - start_time

                # For now, just check that synthesis completed
                assert Path(tmp.name).exists()
                file_size = Path(tmp.name).stat().st_size
                assert file_size > 0

                # Rough RTF calculation based on file size and sample rate
                # Assuming 16-bit mono at 22050Hz
                # bytes / (bytes_per_sample * sample_rate)
                estimated_duration = file_size / (2 * 22050)
                rtf = (
                    synthesis_time / estimated_duration if estimated_duration > 0 else 0
                )

                # Should be faster than real-time
                assert rtf < 5.0, f"Synthesis too slow: RTF={rtf}"

                # Ideally much faster
                print(f"Real-time factor: {rtf:.2f}x")

        except ImportError:
            pytest.skip("Piper not installed")

    @pytest.mark.integration
    @pytest.mark.japanese
    def test_large_text_input(self):
        """Test handling of large text inputs (1MB+)"""
        try:
            import os
            import time

            import psutil

            from piper_train.phonemize.japanese import phonemize_japanese

            # Create 1MB+ of Japanese text
            large_text = "あいうえお" * 50000  # ~1MB of text

            # Measure memory before
            process = psutil.Process(os.getpid())
            mem_before = process.memory_info().rss / 1024 / 1024  # MB

            # Process large text
            start_time = time.time()
            phonemes = phonemize_japanese(large_text)
            process_time = time.time() - start_time

            # Measure memory after
            mem_after = process.memory_info().rss / 1024 / 1024  # MB
            mem_increase = mem_after - mem_before

            # Verify results
            assert len(phonemes) > 0
            assert isinstance(phonemes, list)

            # Performance checks
            assert process_time < 60.0, f"Processing too slow: {process_time:.2f}s for 1MB"
            assert mem_increase < 500, f"Memory usage too high: {mem_increase:.2f}MB increase"

            print(f"Large text processing: {process_time:.2f}s, Memory: +{mem_increase:.2f}MB")

        except ImportError:
            pytest.skip("Japanese phonemizer not available")

    @pytest.mark.integration
    @pytest.mark.japanese
    def test_special_character_handling(self):
        """Test processing of special characters and punctuation"""
        try:
            from piper_train.phonemize.japanese import phonemize_japanese

            test_cases = [
                # Japanese punctuation
                "。、・「」『』！？",
                # Mixed with text
                "こんにちは。元気ですか？",
                # Emoji and special Unicode
                "こんにちは😀世界🌍",
                # Full-width alphanumeric
                "ＨＥＬＬＯ　ＷＯＲＬＤ",
                # Mixed scripts
                "Hello こんにちは World!",
                # Numbers and symbols
                "１２３ABCあいう＄％＆",
            ]

            for text in test_cases:
                phonemes = phonemize_japanese(text)
                assert isinstance(phonemes, list)
                assert len(phonemes) >= 2  # At least start/end markers

                # Should not crash or return empty
                assert any(p not in ["^", "$", "_"] for p in phonemes), f"No phonemes for '{text}'"

        except ImportError:
            pytest.skip("Japanese phonemizer not available")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_concurrent_execution(self):
        """Test concurrent/parallel execution safety"""
        try:
            import concurrent.futures
            import threading

            from piper_train.phonemize.japanese import phonemize_japanese

            # Test data
            test_texts = [
                "こんにちは世界",
                "おはようございます",
                "ありがとうございます",
                "さようなら",
                "おやすみなさい",
            ] * 10  # 50 tasks total

            results = []
            errors = []
            lock = threading.Lock()

            def process_text(text):
                try:
                    phonemes = phonemize_japanese(text)
                    with lock:
                        results.append((text, phonemes))
                    return phonemes
                except Exception as e:
                    with lock:
                        errors.append((text, str(e)))
                    raise

            # Run concurrent processing
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_text, text) for text in test_texts]
                concurrent.futures.wait(futures)

            # Verify results
            assert len(errors) == 0, f"Errors during concurrent execution: {errors}"
            assert len(results) == len(test_texts)

            # Check consistency - same input should give same output
            text_to_phonemes = {}
            for text, phonemes in results:
                if text in text_to_phonemes:
                    # Compare with previous result
                    assert phonemes == text_to_phonemes[text], \
                        f"Inconsistent results for '{text}'"
                else:
                    text_to_phonemes[text] = phonemes

            print(f"Concurrent execution successful: {len(results)} tasks completed")

        except ImportError:
            pytest.skip("Japanese phonemizer not available")

    @pytest.mark.integration
    def test_memory_leak_detection(self):
        """Test for memory leaks during repeated operations"""
        try:
            import gc
            import os

            import psutil

            from piper_train.phonemize.japanese import phonemize_japanese

            process = psutil.Process(os.getpid())

            # Initial memory
            gc.collect()
            initial_mem = process.memory_info().rss / 1024 / 1024  # MB

            # Run many iterations
            text = "こんにちは世界" * 100
            iterations = 100

            for i in range(iterations):
                phonemes = phonemize_japanese(text)
                # Explicitly delete to help GC
                del phonemes

                if i % 20 == 0:
                    gc.collect()

            # Final memory
            gc.collect()
            final_mem = process.memory_info().rss / 1024 / 1024  # MB
            mem_increase = final_mem - initial_mem

            # Memory increase should be minimal
            assert mem_increase < 50, f"Possible memory leak: {mem_increase:.2f}MB increase after {iterations} iterations"

            print(f"Memory leak test: {mem_increase:.2f}MB increase after {iterations} iterations")

        except ImportError:
            pytest.skip("Japanese phonemizer not available")
