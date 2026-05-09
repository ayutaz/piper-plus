"""Utility for downloading Piper voices."""

import json
import logging
import re
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from .file_hash import get_file_hash


# Pattern for validating repo values (only safe characters, no ".." traversal)
_SAFE_REPO_RE = re.compile(r"^[a-zA-Z0-9._\-/]+$")


URL_FORMAT = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{file}"

# piper-plus models use HuggingFace repos directly
PIPER_PLUS_URL_FORMAT = "https://huggingface.co/{repo}/resolve/main/{file}"

# piper-plus specific voice models
PIPER_PLUS_VOICES: dict[str, Any] = {
    "ja_JP-tsukuyomi-chan-medium": {
        "key": "ja_JP-tsukuyomi-chan-medium",
        "name": "tsukuyomi-chan",
        "language": {
            "code": "ja_JP",
            "family": "ja",
            "region": "JP",
            "name_native": "\u65e5\u672c\u8a9e",
            "name_english": "Japanese",
            "country_english": "Japan",
        },
        "quality": "medium",
        "num_speakers": 1,
        "speaker_id_map": {},
        "source": "piper-plus",
        "repo": "ayousanz/piper-plus-tsukuyomi-chan",
        "files": {
            "tsukuyomi-chan-6lang-fp16.onnx": {
                "size_bytes": 39652717,
                "md5_digest": "",
            },
            "config.json": {
                "size_bytes": 6279,
                "md5_digest": "",
            },
        },
        "aliases": ["tsukuyomi", "tsukuyomi-chan", "ja-tsukuyomi"],
        "description": "Tsukuyomi-chan 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT)",
    },
    "ja_JP-css10-6lang-medium": {
        "key": "ja_JP-css10-6lang-medium",
        "name": "css10-6lang",
        "language": {
            "code": "ja_JP",
            "family": "ja",
            "region": "JP",
            "name_native": "\u65e5\u672c\u8a9e",
            "name_english": "Japanese",
            "country_english": "Japan",
        },
        "quality": "medium",
        "num_speakers": 1,
        "speaker_id_map": {},
        "source": "piper-plus",
        "repo": "ayousanz/piper-plus-css10-ja-6lang",
        "files": {
            "css10-ja-6lang-fp16.onnx": {
                "size_bytes": 39652717,
                "md5_digest": "",
            },
            "config.json": {
                "size_bytes": 5912,
                "md5_digest": "",
            },
        },
        "aliases": ["css10", "css10-6lang", "css10-ja", "ja-css10"],
        "description": "CSS10 Japanese 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT, 6841 utterances)",
    },
}

_DIR = Path(__file__).parent
_LOGGER = logging.getLogger(__name__)

_SKIP_FILES = {"MODEL_CARD"}


class VoiceNotFoundError(Exception):
    pass


def get_voices(download_dir: str | Path, update_voices: bool = False) -> dict[str, Any]:
    """Loads available voices from downloaded or embedded JSON file."""
    download_dir = Path(download_dir)
    voices_download = download_dir / "voices.json"

    if update_voices:
        # Download latest voices.json
        voices_url = URL_FORMAT.format(file="voices.json")
        _LOGGER.debug("Downloading %s to %s", voices_url, voices_download)
        with (
            urlopen(voices_url) as response,
            open(voices_download, "wb") as download_file,
        ):
            shutil.copyfileobj(response, download_file)

    # Prefer downloaded file to embedded
    voices_embedded = _DIR / "voices.json"
    voices_path = voices_download if voices_download.exists() else voices_embedded

    _LOGGER.debug("Loading %s", voices_path)
    with open(voices_path, encoding="utf-8") as voices_file:
        voices = json.load(voices_file)

    # Merge piper-plus voices (piper-plus takes precedence)
    voices.update(PIPER_PLUS_VOICES)

    return voices


def ensure_voice_exists(
    name: str,
    data_dirs: Iterable[str | Path],
    download_dir: str | Path,
    voices_info: dict[str, Any],
):
    assert data_dirs, "No data dirs"
    if name not in voices_info:
        raise VoiceNotFoundError(name)

    voice_info = voices_info[name]
    voice_files = voice_info["files"]
    files_to_download: set[str] = set()

    for data_dir in data_dirs:
        data_dir = Path(data_dir)

        # Check sizes/hashes
        for file_path, file_info in voice_files.items():
            if file_path in files_to_download:
                # Already planning to download
                continue

            file_name = Path(file_path).name
            if file_name in _SKIP_FILES:
                continue

            data_file_path = data_dir / file_name
            _LOGGER.debug("Checking %s", data_file_path)
            if not data_file_path.exists():
                _LOGGER.debug("Missing %s", data_file_path)
                files_to_download.add(file_path)
                continue

            expected_size = file_info["size_bytes"]
            actual_size = data_file_path.stat().st_size
            if expected_size != actual_size:
                _LOGGER.warning(
                    "Wrong size (expected=%s, actual=%s) for %s",
                    expected_size,
                    actual_size,
                    data_file_path,
                )
                files_to_download.add(file_path)
                continue

            expected_hash = file_info["md5_digest"]
            if not expected_hash:
                # No hash to verify; accept the file as-is
                continue
            actual_hash = get_file_hash(data_file_path)
            if expected_hash != actual_hash:
                _LOGGER.warning(
                    "Wrong hash (expected=%s, actual=%s) for %s",
                    expected_hash,
                    actual_hash,
                    data_file_path,
                )
                files_to_download.add(file_path)
                continue

    if (not voice_files) and (not files_to_download):
        raise ValueError(f"Unable to find or download voice: {name}")

    # Download missing files
    download_dir = Path(download_dir)

    for file_path in files_to_download:
        file_name = Path(file_path).name
        if file_name in _SKIP_FILES:
            continue

        # piper-plus models use HuggingFace repo URLs
        if voice_info.get("source") == "piper-plus":
            repo = voice_info.get("repo", "")
            if not _SAFE_REPO_RE.match(repo) or ".." in repo:
                raise ValueError(f"Invalid repo value: {repo!r}")
            file_url = PIPER_PLUS_URL_FORMAT.format(
                repo=repo, file=Path(file_path).name
            )
        else:
            file_url = URL_FORMAT.format(file=file_path)

        if not file_url.startswith("https://"):
            raise ValueError(f"Refusing non-HTTPS URL: {file_url}")

        download_file_path = download_dir / file_name
        download_file_path.parent.mkdir(parents=True, exist_ok=True)

        _LOGGER.debug("Downloading %s to %s", file_url, download_file_path)
        with (
            urlopen(file_url) as response,
            open(download_file_path, "wb") as download_file,
        ):
            shutil.copyfileobj(response, download_file)

        _LOGGER.info("Downloaded %s (%s)", download_file_path, file_url)


def find_voice(name: str, data_dirs: Iterable[str | Path]) -> tuple[Path, Path]:
    data_dirs = list(data_dirs)

    # First try the standard naming convention: {name}.onnx / {name}.onnx.json
    for data_dir in data_dirs:
        data_dir = Path(data_dir)
        onnx_path = data_dir / f"{name}.onnx"
        config_path = data_dir / f"{name}.onnx.json"

        if onnx_path.exists() and config_path.exists():
            return onnx_path, config_path

    # For piper-plus models, file names may differ from the voice key.
    # Look up files from the catalog and search by actual file names.
    voice_info = PIPER_PLUS_VOICES.get(name)
    if voice_info and voice_info.get("source") == "piper-plus":
        onnx_file = None
        config_file = None
        for file_name in voice_info.get("files", {}):
            if file_name.endswith(".onnx"):
                onnx_file = file_name
            elif file_name.endswith(".json"):
                config_file = file_name

        if onnx_file and config_file:
            for data_dir in data_dirs:
                data_dir = Path(data_dir)
                onnx_path = data_dir / onnx_file
                config_path = data_dir / config_file

                if onnx_path.exists() and config_path.exists():
                    return onnx_path, config_path

    raise ValueError(f"Missing files for voice {name}")


def list_voices(
    download_dir: str | Path,
    language_filter: str = "",
    update_voices: bool = False,
) -> None:
    """List available voice models.

    Output format matches the C++ listModels() for consistency.
    """
    voices = get_voices(download_dir, update_voices=update_voices)

    # Build a flat list of voice entries with resolved language info
    entries: list[dict[str, Any]] = []
    for voice_key, voice_info in voices.items():
        # Skip alias entries (those injected by callers)
        if voice_info.get("_is_alias"):
            continue

        lang = voice_info.get("language", {})
        lang_code = lang.get("code", "")
        lang_family = lang.get("family", "")

        if language_filter:
            if language_filter not in (lang_family, lang_code):
                continue

        entries.append(
            {
                "key": voice_info.get("key", voice_key),
                "language_code": lang_code,
                "language_family": lang_family,
                "language_name_english": lang.get("name_english", ""),
                "language_name_native": lang.get("name_native", ""),
                "source": voice_info.get("source", "upstream"),
                "num_speakers": voice_info.get("num_speakers", 1),
                "quality": voice_info.get("quality", ""),
            }
        )

    if not entries:
        if language_filter:
            print(
                f"No voice models found for language: {language_filter}",
                file=sys.stderr,
            )
        else:
            print("No voice models found.", file=sys.stderr)
        return

    # Sort by language code, then key
    entries.sort(key=lambda e: (e["language_code"], e["key"]))

    print(file=sys.stderr)
    print("Available voice models:", file=sys.stderr)

    # Group by language code
    current_lang = ""
    for entry in entries:
        if entry["language_code"] != current_lang:
            current_lang = entry["language_code"]
            print(file=sys.stderr)
            name_eng = entry["language_name_english"]
            name_native = entry["language_name_native"]
            header = f"  {name_eng}"
            if name_native and name_native != name_eng:
                header += f" ({name_native})"
            header += f" [{current_lang}]:"
            print(header, file=sys.stderr)

        # Format: key  [source]  N speaker(s)  quality
        key = entry["key"]
        pad_len = max(40 - len(key), 2)
        n = entry["num_speakers"]
        speaker_word = "speaker" if n == 1 else "speakers"
        line = (
            f"    {key}{' ' * pad_len}"
            f"[{entry['source']}]  "
            f"{n} {speaker_word}   "
            f"{entry['quality']}"
        )
        print(line, file=sys.stderr)

    print(file=sys.stderr)
    print(
        "Use --download-model <name> to download a model.",
        file=sys.stderr,
    )
    print(file=sys.stderr)


def download_model(
    name: str,
    download_dir: str | Path,
    update_voices: bool = False,
) -> tuple[Path, Path]:
    """Download a voice model by name or alias. Returns (onnx_path, config_path)."""
    voices = get_voices(download_dir, update_voices=update_voices)

    # Build alias lookup
    aliases: dict[str, Any] = {}
    for _voice_key, voice_info in voices.items():
        for alias in voice_info.get("aliases", []):
            aliases[alias] = voice_info

    # Resolve name
    if name in voices:
        voice_info = voices[name]
    elif name in aliases:
        voice_info = aliases[name]
    else:
        raise VoiceNotFoundError(
            f"Model '{name}' not found. Use --list-models to see available models."
        )

    resolved_key = voice_info.get("key", name)

    # Download
    ensure_voice_exists(resolved_key, [download_dir], download_dir, voices)

    # Return paths
    return find_voice(resolved_key, [download_dir])
