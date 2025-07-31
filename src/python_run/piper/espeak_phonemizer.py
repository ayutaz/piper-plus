#!/usr/bin/env python3
"""eSpeak-NG phonemizer fallback implementation"""

import logging
import subprocess


_LOGGER = logging.getLogger(__name__)


def phonemize_espeak_ng(text: str, voice: str = "en-us") -> list[list[str]]:
    """Use espeak-ng command to phonemize text"""
    try:
        # Run espeak-ng with IPA output
        cmd = ["espeak-ng", "-v", voice, "-x", "-q", "--ipa"]
        result = subprocess.run(
            cmd, input=text, text=True, capture_output=True, check=True
        )

        # Parse IPA output
        ipa_text = result.stdout.strip()
        _LOGGER.debug(f"eSpeak-NG IPA output: {ipa_text}")

        # Convert IPA to phoneme list
        phonemes = []
        for char in ipa_text:
            if char not in [" ", "\n", "\t"]:
                phonemes.append(char)
            elif char == " " and phonemes and phonemes[-1] != " ":
                phonemes.append(" ")

        # Group by sentences (simple approach)
        return [phonemes]

    except subprocess.CalledProcessError as e:
        _LOGGER.error(f"eSpeak-NG failed: {e}")
        # Fallback to character list
        return [list(text)]
    except FileNotFoundError:
        _LOGGER.error("eSpeak-NG not found")
        # Fallback to character list
        return [list(text)]


def phonemize_espeak_phonemes(text: str, voice: str = "en-us") -> list[list[str]]:
    """Use espeak-ng to get phoneme representation"""
    try:
        # Run espeak-ng with phoneme output
        cmd = ["espeak-ng", "-v", voice, "-x", "-q"]
        result = subprocess.run(
            cmd, input=text, text=True, capture_output=True, check=True
        )

        # Parse phoneme output
        phoneme_text = result.stdout.strip()
        _LOGGER.debug(f"eSpeak-NG phoneme output: {phoneme_text}")

        # Split into phonemes
        phonemes = []
        current_phoneme = ""

        for char in phoneme_text:
            if char in "ˈˌːˑ":  # Stress and length markers
                if current_phoneme:
                    phonemes.append(current_phoneme)
                    current_phoneme = ""
                phonemes.append(char)
            elif char == " ":
                if current_phoneme:
                    phonemes.append(current_phoneme)
                    current_phoneme = ""
                phonemes.append(" ")
            else:
                current_phoneme += char

        if current_phoneme:
            phonemes.append(current_phoneme)

        # Group by sentences
        return [phonemes]

    except Exception as e:
        _LOGGER.error(f"eSpeak-NG phonemization failed: {e}")
        return [list(text)]


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.DEBUG)

    test_text = "Hello world"
    print(f"Text: {test_text}")

    # Test IPA
    ipa_phonemes = phonemize_espeak_ng(test_text)
    print(f"IPA phonemes: {ipa_phonemes}")

    # Test phonemes
    phonemes = phonemize_espeak_phonemes(test_text)
    print(f"Phonemes: {phonemes}")
