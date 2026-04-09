"""
Performance benchmarks for phonemization and synthesis
"""

import os
import statistics
import time

import pytest

# Shared helper from conftest.py (auto_eos=False → unconditional "$").
from conftest import phonemize_japanese as _phonemize_japanese  # noqa: E402


try:
    import psutil
except ImportError:
    psutil = None


class TestPerformance:
    """Performance test suite"""

    @pytest.mark.benchmark
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    def test_phonemization_single_conversion(self):
        """Benchmark single text to phoneme conversion"""
        try:
            _phonemize_japanese("テスト")
        except ImportError:
            pytest.skip("Japanese phonemizer not available")

        # Test texts of various lengths
        test_texts = [
            "こんにちは",  # Short
            "今日はとても良い天気ですね。" * 10,  # Medium
            "あいうえおかきくけこさしすせそたちつてとなにぬねの" * 100,  # Long
        ]

        for text in test_texts:
            times = []

            # Warm up
            _phonemize_japanese(text)

            # Benchmark
            for _ in range(10):
                start = time.perf_counter()
                _phonemize_japanese(text)
                end = time.perf_counter()
                times.append(end - start)

            avg_time = statistics.mean(times)
            std_dev = statistics.stdev(times)

            print(f"\nText length: {len(text)} chars")
            print(f"Average time: {avg_time * 1000:.2f}ms")
            print(f"Std dev: {std_dev * 1000:.2f}ms")
            print(f"Min/Max: {min(times) * 1000:.2f}ms / {max(times) * 1000:.2f}ms")

            # Performance criteria
            if len(text) < 20:
                assert avg_time < 0.1, f"Short text too slow: {avg_time:.3f}s"
            elif len(text) < 500:
                assert avg_time < 0.5, f"Medium text too slow: {avg_time:.3f}s"
            else:
                assert avg_time < 2.0, f"Long text too slow: {avg_time:.3f}s"

    @pytest.mark.benchmark
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_batch_conversion_performance(self):
        """Benchmark batch text processing"""
        try:
            _phonemize_japanese("テスト")
        except ImportError:
            pytest.skip("Japanese phonemizer not available")

        # Create batch of texts
        batch_sizes = [10, 50, 100]
        base_text = "これはバッチ処理のテストです。"

        for batch_size in batch_sizes:
            texts = [base_text + str(i) for i in range(batch_size)]

            # Measure batch processing
            start = time.perf_counter()
            results = [_phonemize_japanese(text) for text in texts]
            end = time.perf_counter()

            total_time = end - start
            per_text_time = total_time / batch_size

            print(f"\nBatch size: {batch_size}")
            print(f"Total time: {total_time:.2f}s")
            print(f"Per text: {per_text_time * 1000:.2f}ms")
            print(f"Throughput: {batch_size / total_time:.1f} texts/sec")

            # All results should be valid
            assert len(results) == batch_size
            assert all(len(r) > 0 for r in results)

            # Throughput should be reasonable
            assert batch_size / total_time > 5, (
                f"Throughput too low: {batch_size / total_time:.1f} texts/sec"
            )

    @pytest.mark.benchmark
    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    def test_memory_usage_measurement(self):
        """Measure memory usage during operations"""
        try:
            _phonemize_japanese("テスト")
        except ImportError:
            pytest.skip("Japanese phonemizer not available")

        import gc

        process = psutil.Process(os.getpid())

        # Force garbage collection
        gc.collect()

        # Baseline memory
        baseline_mem = process.memory_info().rss / 1024 / 1024  # MB

        # Process increasingly large texts
        text_sizes = [100, 1000, 10000, 50000]
        memory_usage = []

        for size in text_sizes:
            text = "あ" * size

            # Measure memory before
            gc.collect()
            mem_before = process.memory_info().rss / 1024 / 1024

            # Process text
            phonemes = _phonemize_japanese(text)

            # Measure memory after
            mem_after = process.memory_info().rss / 1024 / 1024
            mem_increase = mem_after - mem_before

            memory_usage.append(
                {
                    "text_size": size,
                    "mem_increase": mem_increase,
                    "output_size": len(phonemes),
                }
            )

            print(f"\nText size: {size} chars")
            print(f"Memory increase: {mem_increase:.2f}MB")
            print(f"Output size: {len(phonemes)} phonemes")

            # Memory usage should be reasonable
            assert mem_increase < size * 0.001, (
                f"Memory usage too high: {mem_increase:.2f}MB for {size} chars"
            )

            # Clean up
            del text, phonemes
            gc.collect()

        # Final memory should not be much higher than baseline
        final_mem = process.memory_info().rss / 1024 / 1024
        total_increase = final_mem - baseline_mem

        print(f"\nTotal memory increase: {total_increase:.2f}MB")
        assert total_increase < 100, (
            f"Possible memory leak: {total_increase:.2f}MB total increase"
        )

    @pytest.mark.benchmark
    @pytest.mark.slow
    def test_stress_test(self):
        """Stress test with extreme inputs"""
        try:
            _phonemize_japanese("テスト")
        except ImportError:
            pytest.skip("Japanese phonemizer not available")

        try:
            # Long text (~5KB, safe for pyopenjtalk)
            very_long_text = "あいうえおかきくけこ" * 500

            start = time.perf_counter()
            phonemes = _phonemize_japanese(very_long_text)
            end = time.perf_counter()

            process_time = end - start

            print("\nStress test results:")
            print(
                f"Input size: {len(very_long_text)} chars ({len(very_long_text) / 1024:.1f}KB)"
            )
            print(f"Output size: {len(phonemes)} phonemes")
            print(f"Processing time: {process_time:.2f}s")
            print(f"Throughput: {len(very_long_text) / process_time:.0f} chars/sec")

            # Should complete within reasonable time
            assert process_time < 30.0, f"Stress test too slow: {process_time:.2f}s"

            # Output should be proportional to input
            assert len(phonemes) > len(very_long_text), "Output seems too small"

        except RuntimeError:
            pytest.skip("pyopenjtalk crashed on long input (known limitation)")

    @pytest.mark.benchmark
    @pytest.mark.requires_model
    def test_synthesis_performance(self):
        """Test synthesis performance with timing"""
        try:
            import tempfile
            from pathlib import Path

            from piper.voice import PiperVoice

            model_path = Path("test/models/multilingual-test-medium.onnx")
            if not model_path.exists():
                pytest.skip("Japanese test model not available")

            voice = PiperVoice.load(str(model_path))

            # Test texts
            test_cases = [
                ("short", "こんにちは"),
                ("medium", "今日は良い天気ですね。散歩に行きましょう。"),
                ("long", "これは長いテキストのテストです。" * 10),
            ]

            for name, text in test_cases:
                times = []

                # Warm up
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                    voice.synthesize(text, tmp.name)

                # Benchmark
                for _ in range(5):
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                        start = time.perf_counter()
                        voice.synthesize(text, tmp.name)
                        end = time.perf_counter()
                        times.append(end - start)

                        # Estimate audio duration from file size
                        file_size = Path(tmp.name).stat().st_size
                        # 16-bit mono at 22050Hz = 44100 bytes/sec
                        audio_duration = file_size / 44100

                avg_time = statistics.mean(times)
                rtf = avg_time / audio_duration if audio_duration > 0 else 0

                print(f"\n{name.capitalize()} text synthesis:")
                print(f"Text length: {len(text)} chars")
                print(f"Average time: {avg_time:.3f}s")
                print(f"Audio duration: {audio_duration:.2f}s")
                print(f"Real-time factor: {rtf:.2f}x")

                # Should be faster than real-time
                assert rtf < 2.0, f"Synthesis too slow: RTF={rtf:.2f}"

        except ImportError:
            pytest.skip("Piper not installed")


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-m", "benchmark"])
