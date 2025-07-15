#!/usr/bin/env python3
"""
Verify multilingual setup and test basic functionality.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)


def check_dependencies():
    """Check if all required dependencies are available."""
    print("Checking dependencies...")

    dependencies_ok = True

    # Check pyopenjtalk
    try:
        import importlib.util
        spec = importlib.util.find_spec("pyopenjtalk")
        if spec is not None:
            print("✓ pyopenjtalk is installed")
            dependencies_ok = True
        else:
            print("✗ pyopenjtalk is NOT installed (required for Japanese)")
            print("  Install with: pip install pyopenjtalk")
            dependencies_ok = False
    except ImportError:
        print("✗ pyopenjtalk is NOT installed (required for Japanese)")
        print("  Install with: pip install pyopenjtalk")
        dependencies_ok = False

    # Check for piper_phonemize (optional for this test)
    try:
        import importlib.util
        spec = importlib.util.find_spec("piper_phonemize")
        if spec is not None:
            print("✓ piper_phonemize is installed")
        else:
            print("⚠ piper_phonemize is NOT installed (required for non-Japanese languages)")
            print("  This is expected if you haven't installed the full piper package")
    except ImportError:
        print("⚠ piper_phonemize is NOT installed (required for non-Japanese languages)")
        print("  This is expected if you haven't installed the full piper package")

    # Check our modules
    try:
        import importlib.util
        spec = importlib.util.find_spec("piper_train.phonemize.multilingual_phoneme_map")
        if spec is not None:
            from piper_train.phonemize.multilingual_phoneme_map import (
                get_multilingual_phoneme_mapper,  # noqa: F401
            )
            print("✓ Multilingual phoneme mapper is available")
        else:
            print("✗ Failed to find multilingual phoneme mapper module")
            dependencies_ok = False
    except ImportError as e:
        print(f"✗ Failed to import multilingual phoneme mapper: {e}")
        dependencies_ok = False

    try:
        import importlib.util
        spec = importlib.util.find_spec("piper_train.phonemize.multilingual")
        if spec is not None:
            from piper_train.phonemize.multilingual import (
                MultilingualPhonemizer,  # noqa: F401
            )
            print("✓ Multilingual phonemizer is available")
        else:
            print("⚠ Multilingual phonemizer module not found")
            print("  This is expected if piper_phonemize is not installed")
    except ImportError as e:
        print(f"⚠ Failed to import multilingual phonemizer: {e}")
        print("  This is expected if piper_phonemize is not installed")

    return dependencies_ok


def test_phoneme_mapping():
    """Test the phoneme mapping functionality."""
    print("\nTesting phoneme mapping...")

    try:
        from piper_train.phonemize.multilingual_phoneme_map import (
            get_multilingual_phoneme_mapper,
        )

        mapper = get_multilingual_phoneme_mapper()
        print(f"✓ Total vocabulary size: {mapper.get_vocab_size()}")

        # Test some mappings
        test_cases = [
            ("<pad>", "", 0),
            ("<lang:ja>", "", 10),
            ("a", "ja", 100),
            ("k", "ja", 110),
        ]

        all_ok = True
        for phoneme, lang, expected in test_cases:
            actual = mapper.get_phoneme_id(phoneme, lang)
            if actual == expected:
                print(f"✓ {lang}:{phoneme} -> {actual}")
            else:
                print(f"✗ {lang}:{phoneme} -> {actual} (expected {expected})")
                all_ok = False

        return all_ok
    except Exception as e:
        print(f"✗ Error testing phoneme mapping: {e}")
        return False


def test_japanese_phonemization():
    """Test Japanese phonemization."""
    print("\nTesting Japanese phonemization...")

    try:
        from piper_train.phonemize.japanese import phonemize_japanese

        test_text = "こんにちは"
        phonemes = phonemize_japanese(test_text)

        print(f"✓ Text: {test_text}")
        print(f"✓ Phonemes: {phonemes}")
        print(f"✓ Number of phonemes: {len(phonemes)}")

        return len(phonemes) > 0
    except Exception as e:
        print(f"✗ Error testing Japanese phonemization: {e}")
        return False


def test_dataset_format():
    """Test dataset format creation."""
    print("\nTesting dataset format...")

    try:
        from piper_train.phonemize.multilingual_dataset import (
            MultilingualDatasetFormatter,
        )

        formatter = MultilingualDatasetFormatter()

        # Create a test utterance
        utt = formatter.format_utterance(
            text="こんにちは",
            audio_path="test.wav",
            duration=1.5,
            speaker_id=0,
            primary_language="ja"
        )

        print(f"✓ Created utterance for: {utt.text}")
        print(f"✓ Language: {utt.text_language}")
        print(f"✓ Number of phonemes: {len(utt.phonemes)}")
        print(f"✓ Number of phoneme IDs: {len(utt.phoneme_ids)}")

        # Test serialization
        data = utt.to_dict()
        print(f"✓ Serialization successful, keys: {list(data.keys())}")

        return True
    except Exception as e:
        print(f"✗ Error testing dataset format: {e}")
        return False


def check_preprocessing_script():
    """Check if preprocessing scripts exist."""
    print("\nChecking preprocessing scripts...")

    scripts = [
        "scripts/preprocess_multilingual_dataset.py",
        "scripts/run_multilingual_preprocessing.sh",
        "scripts/prepare_multilingual_dataset.py",
    ]

    all_exist = True
    for script in scripts:
        path = Path(script)
        if path.exists():
            print(f"✓ {script} exists")
        else:
            print(f"✗ {script} NOT found")
            all_exist = False

    return all_exist


def check_model_files():
    """Check if model files exist."""
    print("\nChecking model files...")

    files = [
        "src/python/piper_train/vits/models_multilingual.py",
        "src/python/piper_train/vits/lightning_multilingual.py",
        "src/python/piper_train/vits/dataset_multilingual.py",
        "src/python/piper_train/train_multilingual.py",
    ]

    all_exist = True
    for file in files:
        path = Path(file)
        if path.exists():
            print(f"✓ {file} exists")
        else:
            print(f"✗ {file} NOT found")
            all_exist = False

    return all_exist


def main():
    print("=" * 60)
    print("Multilingual VITS Setup Verification")
    print("=" * 60)

    all_ok = True

    # Run all checks
    all_ok &= check_dependencies()
    all_ok &= test_phoneme_mapping()
    all_ok &= test_japanese_phonemization()
    all_ok &= test_dataset_format()
    all_ok &= check_preprocessing_script()
    all_ok &= check_model_files()

    print("\n" + "=" * 60)
    if all_ok:
        print("✓ All checks passed! Multilingual setup is ready.")
        print("\nNext steps:")
        print("1. Prepare your datasets in LJSpeech format")
        print("2. Create a configuration file (see examples/multilingual_dataset_example.json)")
        print("3. Run preprocessing:")
        print("   ./scripts/run_multilingual_preprocessing.sh -c your_config.json -o output_dir")
        print("4. Train the model:")
        print("   python -m piper_train.train_multilingual --dataset-dir output_dir")
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        print("\nMain issues to resolve:")
        print("- Install missing dependencies")
        print("- Ensure all files are properly created")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
