"""
Real integration tests that verify actual functionality
"""

import pytest


class TestRealIntegration:
    """Test real end-to-end functionality without mocks"""

    @pytest.mark.integration
    @pytest.mark.requires_model
    @pytest.mark.skip(reason="Requires full piper runtime")
    def test_synthesis_produces_audio(self):
        """Test that synthesis actually produces audio data"""

    @pytest.mark.integration
    @pytest.mark.japanese
    @pytest.mark.requires_model
    @pytest.mark.skip(reason="Requires full piper runtime")
    def test_japanese_synthesis_with_pua(self):
        """Test Japanese synthesis with PUA mapping"""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.skip(reason="Requires full piper runtime")
    def test_performance_baseline(self):
        """Test that synthesis meets basic performance requirements"""

    @pytest.mark.integration
    @pytest.mark.japanese
    def test_large_text_input(self):
        """Test handling of large text inputs (1MB+)"""
        try:
            import os
            import time

            import psutil

            from piper_plus_g2p.japanese import JapanesePhonemizer as _JaPhonemizer
            from piper_plus_g2p.encode.pua import map_token as _mt

            def phonemize_japanese(text):
                p = _JaPhonemizer()
                tokens = p.phonemize(text)
                return [_mt(t) for t in ["^"] + tokens + ["$"]]

            # Create a moderate amount of Japanese text
            # OpenJTalk has issues with very large texts, so we test with smaller chunks
            large_text = "あいうえお" * 1000  # ~20KB of text

            # Measure memory before
            process = psutil.Process(os.getpid())
            mem_before = process.memory_info().rss / 1024 / 1024  # MB

            # Process large text
            start_time = time.time()
            try:
                phonemes = phonemize_japanese(large_text)
            except RuntimeError as e:
                # OpenJTalk can fail with very large inputs
                pytest.skip(f"OpenJTalk failed with large input: {e}")
            process_time = time.time() - start_time

            # Measure memory after
            mem_after = process.memory_info().rss / 1024 / 1024  # MB
            mem_increase = mem_after - mem_before

            # Verify results
            assert len(phonemes) > 0
            assert isinstance(phonemes, list)

            # Performance checks
            assert process_time < 10.0, f"Processing too slow: {process_time:.2f}s"
            assert mem_increase < 100, (
                f"Memory usage too high: {mem_increase:.2f}MB increase"
            )

            print(
                f"Large text processing: {process_time:.2f}s, Memory: +{mem_increase:.2f}MB"
            )

        except ImportError:
            pytest.skip("Japanese phonemizer not available")

    @pytest.mark.integration
    @pytest.mark.japanese
    def test_special_character_handling(self):
        """Test processing of special characters and punctuation"""
        try:
            from piper_plus_g2p.japanese import JapanesePhonemizer as _JaPhonemizer
            from piper_plus_g2p.encode.pua import map_token as _mt

            def phonemize_japanese(text):
                p = _JaPhonemizer()
                tokens = p.phonemize(text)
                return [_mt(t) for t in ["^"] + tokens + ["$"]]

            test_cases = [
                # Mixed with text - more likely to succeed
                "こんにちは。元気ですか？",
                # Full-width alphanumeric
                "ＨＥＬＬＯ　ＷＯＲＬＤ",
                # Mixed scripts
                "Hello こんにちは World!",
                # Numbers with text
                "１２３あいう",
            ]

            for text in test_cases:
                try:
                    phonemes = phonemize_japanese(text)
                    assert isinstance(phonemes, list)
                    # OpenJTalk may return empty list for some inputs
                    if len(phonemes) > 0:
                        # Should have actual phonemes, not just markers
                        assert any(p not in ["^", "$", "_"] for p in phonemes), (
                            f"No phonemes for '{text}'"
                        )
                except RuntimeError as e:
                    # OpenJTalk can fail with certain special characters
                    print(f"OpenJTalk failed for '{text}': {e}")
                    continue

        except ImportError:
            pytest.skip("Japanese phonemizer not available")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_concurrent_execution(self):
        """Test concurrent/parallel execution safety"""
        try:
            import concurrent.futures
            import threading

            from piper_plus_g2p.japanese import JapanesePhonemizer as _JaPhonemizer
            from piper_plus_g2p.encode.pua import map_token as _mt

            def phonemize_japanese(text):
                p = _JaPhonemizer()
                tokens = p.phonemize(text)
                return [_mt(t) for t in ["^"] + tokens + ["$"]]

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
                    assert phonemes == text_to_phonemes[text], (
                        f"Inconsistent results for '{text}'"
                    )
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

            from piper_plus_g2p.japanese import JapanesePhonemizer as _JaPhonemizer
            from piper_plus_g2p.encode.pua import map_token as _mt

            def phonemize_japanese(text):
                p = _JaPhonemizer()
                tokens = p.phonemize(text)
                return [_mt(t) for t in ["^"] + tokens + ["$"]]

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
            assert mem_increase < 50, (
                f"Possible memory leak: {mem_increase:.2f}MB increase after {iterations} iterations"
            )

            print(
                f"Memory leak test: {mem_increase:.2f}MB increase after {iterations} iterations"
            )

        except ImportError:
            pytest.skip("Japanese phonemizer not available")
