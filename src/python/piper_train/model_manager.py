"""Model manager for piper-plus voice catalog.

Provides model listing, downloading, and resolution functionality
matching the C++ model_manager.cpp and C# ModelManager.cs implementations.
"""

import os
import sys


# Embedded voice catalog (matches src/cpp/piper_plus_voices.json)
_BUILTIN_CATALOG = {
    "ja_JP-tsukuyomi-chan-medium": {
        "key": "ja_JP-tsukuyomi-chan-medium",
        "name": "tsukuyomi-chan",
        "language_code": "ja_JP",
        "language_family": "ja",
        "language_name_native": "\u65e5\u672c\u8a9e",
        "language_name_english": "Japanese",
        "quality": "medium",
        "num_speakers": 1,
        "source": "piper-plus",
        "repo_id": "ayousanz/piper-plus-tsukuyomi-chan",
        "files": {
            "tsukuyomi-chan-6lang-fp16.onnx": {"size_bytes": 39652717},
            "config.json": {"size_bytes": 6279},
        },
        "aliases": ["tsukuyomi", "tsukuyomi-chan", "ja-tsukuyomi"],
        "description": "Tsukuyomi-chan 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT)",
    },
    "ja_JP-css10-6lang-medium": {
        "key": "ja_JP-css10-6lang-medium",
        "name": "css10-6lang",
        "language_code": "ja_JP",
        "language_family": "ja",
        "language_name_native": "\u65e5\u672c\u8a9e",
        "language_name_english": "Japanese",
        "quality": "medium",
        "num_speakers": 1,
        "source": "piper-plus",
        "repo_id": "ayousanz/piper-plus-css10-ja-6lang",
        "files": {
            "css10-ja-6lang-fp16.onnx": {"size_bytes": 39652717},
            "config.json": {"size_bytes": 5912},
        },
        "aliases": ["css10", "css10-6lang", "css10-ja", "ja-css10"],
        "description": "CSS10 Japanese 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT, 6841 utterances)",
    },
}


def get_default_model_dir() -> str:
    """Return the default model directory (OS-specific).

    Checks PIPER_MODEL_DIR env var first, then falls back to:
    - Windows: %APPDATA%/piper/models
    - macOS: ~/Library/Application Support/piper/models
    - Linux: $XDG_DATA_HOME/piper/models or ~/.local/share/piper/models
    """
    env_dir = os.environ.get("PIPER_MODEL_DIR")
    if env_dir:
        return env_dir

    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "piper", "models")
    elif sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", "piper", "models"
        )
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return os.path.join(xdg, "piper", "models")
        return os.path.join(
            os.path.expanduser("~"), ".local", "share", "piper", "models"
        )


def find_voice(name: str) -> dict | None:
    """Find a voice by key, name, or alias.

    Returns the voice dict or None if not found.
    """
    if not name:
        return None

    # Exact key match
    if name in _BUILTIN_CATALOG:
        return _BUILTIN_CATALOG[name]

    # Search by name or alias
    for voice in _BUILTIN_CATALOG.values():
        if voice["name"] == name:
            return voice
        if name in voice.get("aliases", []):
            return voice

    return None


def list_models(language_filter: str | None = None) -> None:
    """Print available voice models to stderr.

    Args:
        language_filter: Optional language code (e.g., "ja" or "ja_JP") to filter by.
    """
    voices = list(_BUILTIN_CATALOG.values())

    if language_filter:
        voices = [
            v
            for v in voices
            if v["language_family"] == language_filter
            or v["language_code"] == language_filter
        ]

    if not voices:
        if language_filter:
            print(
                f"No voice models found for language: {language_filter}",
                file=sys.stderr,
            )
        else:
            print("No voice models found.", file=sys.stderr)
        return

    print("\nAvailable voice models:", file=sys.stderr)

    current_lang = ""
    for voice in sorted(voices, key=lambda v: (v["language_code"], v["key"])):
        if voice["language_code"] != current_lang:
            current_lang = voice["language_code"]
            header = f"  {voice['language_name_english']}"
            if (
                voice.get("language_name_native")
                and voice["language_name_native"] != voice["language_name_english"]
            ):
                header += f" ({voice['language_name_native']})"
            header += f" [{current_lang}]:"
            print(f"\n{header}", file=sys.stderr)

        speakers = (
            "1 speaker"
            if voice["num_speakers"] == 1
            else f"{voice['num_speakers']} speakers"
        )
        print(
            f"    {voice['key']:<44} [{voice['source']}]  {speakers}   {voice['quality']}",
            file=sys.stderr,
        )

    print("\nUse --download-model <name> to download a model.", file=sys.stderr)


def download_model(model_name: str, model_dir: str | None = None) -> bool:
    """Download a model by name/alias to the model directory.

    Returns True on success, False on failure.
    """
    voice = find_voice(model_name)
    if voice is None:
        print(
            f"Error: Model '{model_name}' not found. Use --list-models to see available models.",
            file=sys.stderr,
        )
        return False

    if model_dir is None:
        model_dir = get_default_model_dir()

    os.makedirs(model_dir, exist_ok=True)

    print(f"Downloading model: {voice['key']} ({voice['source']})", file=sys.stderr)

    repo_id = voice["repo_id"]

    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
    except ImportError:
        print(
            "Error: huggingface_hub is required for model download. "
            "Install with: pip install huggingface-hub",
            file=sys.stderr,
        )
        return False

    success = True
    for filename, file_info in voice["files"].items():
        dest_path = os.path.join(model_dir, filename)

        # Skip if file already exists with correct size
        if os.path.exists(dest_path):
            existing_size = os.path.getsize(dest_path)
            expected_size = file_info.get("size_bytes", 0)
            if expected_size > 0 and existing_size == expected_size:
                print(
                    f"  Skipping {filename} (already exists, size matches)",
                    file=sys.stderr,
                )
                continue

        try:
            print(f"  Downloading {filename}...", file=sys.stderr)
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=model_dir,
                local_dir_use_symlinks=False,
            )
            print(f"  Saved to {dest_path}", file=sys.stderr)
        except Exception as e:
            print(f"  Failed to download {filename}: {e}", file=sys.stderr)
            success = False

    if success:
        print(f"\nModel downloaded to: {model_dir}", file=sys.stderr)

        # Print usage hint
        onnx_files = [f for f in voice["files"] if f.endswith(".onnx")]
        if onnx_files:
            onnx_path = os.path.join(model_dir, onnx_files[0])
            print("\nUsage:", file=sys.stderr)
            print(
                f"  python -m piper_train.infer_onnx --model {onnx_path} "
                f"--text '\u3053\u3093\u306b\u3061\u306f' --output-dir ./output",
                file=sys.stderr,
            )

    return success


def resolve_model_path(model_arg: str, model_dir: str | None = None) -> str | None:
    """Resolve a model argument to an actual .onnx file path.

    If model_arg is a file path that exists, return it directly.
    If it's a model name/alias, look for the downloaded model in model_dir.

    Returns the resolved path or None if not found.
    """
    # Direct file path
    if os.path.exists(model_arg):
        return model_arg

    # Try as model name/alias
    voice = find_voice(model_arg)
    if voice is None:
        return None

    if model_dir is None:
        model_dir = get_default_model_dir()

    # Find the ONNX file
    for filename in voice["files"]:
        if filename.endswith(".onnx"):
            path = os.path.join(model_dir, filename)
            if os.path.exists(path):
                return path

    return None
