#!/usr/bin/env python3
import argparse
import csv
import dataclasses
import itertools
import json
import logging
import os
import signal
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from multiprocessing import JoinableQueue, Process, Queue
from pathlib import Path


try:
    from piper_phonemize import (
        get_codepoints_map,
        get_espeak_map,
        get_max_phonemes,
        phoneme_ids_codepoints,
        phoneme_ids_espeak,
        phonemize_codepoints,
        phonemize_espeak,
        tashkeel_run,
    )

    _PIPER_PHONEMIZE_AVAILABLE = True
except ImportError:
    _PIPER_PHONEMIZE_AVAILABLE = False
from tqdm import tqdm


try:
    from piper_phonemize import (  # noqa: PLC0415
        get_codepoints_map,
        get_espeak_map,
        get_max_phonemes,
        phoneme_ids_codepoints,
        phoneme_ids_espeak,
        phonemize_codepoints,
        phonemize_espeak,
        tashkeel_run,
    )
except ImportError:
    # piper_phonemize is not available on Windows; only needed for espeak languages
    get_codepoints_map = None
    get_espeak_map = None
    get_max_phonemes = None
    phoneme_ids_codepoints = None
    phoneme_ids_espeak = None
    phonemize_codepoints = None
    phonemize_espeak = None
    tashkeel_run = None

# piper_plus_g2p: G2P and encoding
from piper_plus_g2p.custom_dict import CustomDictionary
from piper_plus_g2p.encode.encoder import PiperEncoder
from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_plus_g2p.encode.pua import map_token
from piper_plus_g2p.japanese import JapanesePhonemizer
from piper_plus_g2p.multilingual import MultilingualPhonemizer, UnicodeLanguageDetector

from .f0_extraction import cache_f0
from .norm_audio import cache_norm_audio, cache_norm_audio_fast, make_silence_detector


_DIR = Path(__file__).parent
_VERSION = (_DIR / "VERSION").read_text(encoding="utf-8").strip()
_LOGGER = logging.getLogger("preprocess")

# signal.SIGALRM / signal.alarm() are Unix-only; guard all uses.
_HAS_SIGALRM = hasattr(signal, "SIGALRM")


class PhonemeType(StrEnum):
    ESPEAK = "espeak"
    """Phonemes come from espeak-ng"""

    TEXT = "text"
    """Phonemes come from text itself"""

    OPENJTALK = "openjtalk"
    """Phonemes come from pyopenjtalk for Japanese"""

    BILINGUAL = "bilingual"
    """Phonemes come from bilingual phonemizer (JA+EN)"""

    MULTILINGUAL = "multilingual"
    """Phonemes come from multilingual phonemizer (N languages)"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir", required=True, help="Directory with audio dataset"
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write output files for training",
    )
    parser.add_argument("--language", required=True, help="eSpeak-ng voice")
    parser.add_argument(
        "--sample-rate",
        type=int,
        required=True,
        help="Target sample rate for voice (hertz)",
    )
    parser.add_argument(
        "--dataset-format", choices=("ljspeech", "mycroft"), required=True
    )
    parser.add_argument("--cache-dir", help="Directory to cache processed audio files")
    parser.add_argument("--max-workers", type=int)
    parser.add_argument(
        "--single-speaker", action="store_true", help="Force single speaker dataset"
    )
    parser.add_argument(
        "--speaker-id", type=int, help="Add speaker id to single speaker dataset"
    )
    parser.add_argument(
        "--phoneme-type",
        choices=list(PhonemeType),
        default=PhonemeType.ESPEAK,
        help="Type of phonemes to use (default: espeak)",
    )
    parser.add_argument(
        "--text-casing",
        choices=("ignore", "lower", "upper", "casefold"),
        default="ignore",
        help="Casing applied to utterance text",
    )
    parser.add_argument(
        "--dataset-name",
        help="Name of dataset to put in config (default: name of <ouput_dir>/../)",
    )
    parser.add_argument(
        "--audio-quality",
        help="Audio quality to put in config (default: name of <output_dir>)",
    )
    parser.add_argument(
        "--tashkeel",
        action="store_true",
        help="Diacritize Arabic text with libtashkeel",
    )
    parser.add_argument(
        "--skip-audio", action="store_true", help="Don't preprocess audio"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Timeout in seconds for processing utterances",
    )
    parser.add_argument(
        "--extract-f0",
        action="store_true",
        help="Extract F0 values for training (requires pyworld)",
    )
    parser.add_argument(
        "--f0-min",
        type=float,
        default=80.0,
        help="Minimum F0 value in Hz (default: 80.0)",
    )
    parser.add_argument(
        "--f0-max",
        type=float,
        default=880.0,
        help="Maximum F0 value in Hz (default: 880.0)",
    )
    parser.add_argument(
        "--energy-vad",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use fast energy-based VAD instead of Silero ONNX VAD "
        "(~50x faster, default: enabled). Use --no-energy-vad to "
        "fall back to Silero VAD.",
    )
    args = parser.parse_args()

    if args.single_speaker and (args.speaker_id is not None):
        _LOGGER.fatal("--single-speaker and --speaker-id cannot both be provided")
        return

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=level)
    logging.getLogger().setLevel(level)

    # Prevent log spam
    logging.getLogger("numba").setLevel(logging.WARNING)

    # pyopenjtalkの警告メッセージを抑制（プログレスバーの表示を妨げないため）
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning)

    # Log VAD mode
    if args.energy_vad:
        _LOGGER.info("Using energy-based VAD (fast mode, ~50x faster than Silero)")
    else:
        _LOGGER.info("Using Silero ONNX VAD (--no-energy-vad)")

    # Ensure enum
    args.phoneme_type = PhonemeType(args.phoneme_type)

    # 日本語の場合は自動的に OPENJTALK を使用し、ID マップを設定
    japanese_id_map = None
    bilingual_id_map = None
    multilingual_id_map = None
    lang_parts = args.language.split("-")
    if len(lang_parts) >= 3:
        # Multilingual mode: 3+ languages (e.g., ja-en-zh-ko)
        args.phoneme_type = PhonemeType.MULTILINGUAL
        multilingual_id_map = get_phoneme_id_map("-".join(sorted(lang_parts)))
        args.phoneme_id_map = multilingual_id_map
        args.lang_parts = lang_parts
        _LOGGER.info(
            "Using multilingual (%s) phonemization (%s symbols)",
            args.language,
            len(multilingual_id_map),
        )
    elif args.language == "ja-en":
        args.phoneme_type = PhonemeType.BILINGUAL
        bilingual_id_map = get_phoneme_id_map("ja-en")
        args.phoneme_id_map = bilingual_id_map
        _LOGGER.info(
            "Using bilingual (JA+EN) phonemization (%s symbols)",
            len(bilingual_id_map),
        )
    elif args.language == "ja":
        args.phoneme_type = PhonemeType.OPENJTALK
        japanese_id_map = get_phoneme_id_map("ja")
        args.phoneme_id_map = japanese_id_map  # 子プロセスへ渡すため
        _LOGGER.info(
            "Using pyopenjtalk for Japanese phonemization (%s symbols)",
            len(japanese_id_map),
        )

    # Convert to paths and create output directories
    args.input_dir = Path(args.input_dir)
    args.output_dir = Path(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    args.cache_dir = (
        Path(args.cache_dir)
        if args.cache_dir
        else args.output_dir / "cache" / str(args.sample_rate)
    )
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    if args.dataset_format == "mycroft":
        make_dataset = mycroft_dataset
    else:
        make_dataset = ljspeech_dataset

    # Count speakers
    _LOGGER.debug("Counting number of speakers/utterances in the dataset")
    speaker_counts: Counter[str] = Counter()
    num_utterances = 0
    for utt in make_dataset(args):
        speaker = utt.speaker or ""
        speaker_counts[speaker] += 1
        num_utterances += 1

    assert num_utterances > 0, "No utterances found"

    is_multispeaker = len(speaker_counts) > 1
    speaker_ids: dict[str, int] = {}

    if is_multispeaker:
        _LOGGER.info("%s speakers detected", len(speaker_counts))

        # Assign speaker ids by most number of utterances first
        for speaker_id, (speaker, _speaker_count) in enumerate(
            speaker_counts.most_common()
        ):
            speaker_ids[speaker] = speaker_id
    else:
        _LOGGER.info("Single speaker dataset")

    # Write config
    audio_quality = args.audio_quality or args.output_dir.name
    dataset_name = args.dataset_name or args.output_dir.parent.name

    with open(args.output_dir / "config.json", "w", encoding="utf-8") as config_file:
        json.dump(
            {
                "dataset": dataset_name,
                "audio": {
                    "sample_rate": args.sample_rate,
                    "quality": audio_quality,
                },
                "espeak": {
                    "voice": args.language,
                },
                "language": {
                    "code": args.language,
                },
                "inference": {"noise_scale": 0.667, "length_scale": 1, "noise_w": 0.8},
                "phoneme_type": args.phoneme_type.value,
                "phoneme_map": {},
                "phoneme_id_map": (
                    multilingual_id_map
                    if multilingual_id_map is not None
                    else (
                        bilingual_id_map
                        if bilingual_id_map is not None
                        else (
                            get_codepoints_map()[args.language]
                            if args.phoneme_type == PhonemeType.TEXT
                            else (
                                japanese_id_map
                                if japanese_id_map is not None
                                else get_espeak_map()
                            )
                        )
                    )
                ),
                "num_symbols": (
                    len(multilingual_id_map)
                    if multilingual_id_map is not None
                    else (
                        len(bilingual_id_map)
                        if bilingual_id_map is not None
                        else (
                            len(japanese_id_map)
                            if japanese_id_map is not None
                            else get_max_phonemes()
                        )
                    )
                ),
                "num_speakers": len(speaker_counts),
                "speaker_id_map": speaker_ids,
                "piper_version": _VERSION,
                # Multi-language support
                **(
                    {
                        "num_languages": len(lang_parts),
                        "language_id_map": {
                            lang: idx for idx, lang in enumerate(lang_parts)
                        },
                    }
                    if multilingual_id_map is not None
                    else (
                        {
                            "num_languages": 2,
                            "language_id_map": {"ja": 0, "en": 1},
                        }
                        if bilingual_id_map is not None
                        else {}
                    )
                ),
                # Add prosody information for Japanese, bilingual, or multilingual
                **(
                    {
                        "prosody_num_symbols": 11,
                        "prosody_id_map": {str(i): [i] for i in range(11)},
                    }
                    if args.language in ("ja", "ja-en")
                    or (multilingual_id_map is not None and "ja" in lang_parts)
                    else {}
                ),
            },
            config_file,
            ensure_ascii=True,
            indent=4,
        )
    _LOGGER.info("Wrote dataset config")

    if (args.max_workers is None) or (args.max_workers < 1):
        args.max_workers = os.cpu_count()

    assert args.max_workers is not None

    batch_size = int(num_utterances / (args.max_workers * 2))
    queue_in: Queue[Iterable[Utterance]] = JoinableQueue()
    queue_out: Queue[Utterance | None] = Queue()

    # Start workers
    if args.phoneme_type == PhonemeType.MULTILINGUAL:
        target = phonemize_batch_multilingual
    elif args.phoneme_type == PhonemeType.BILINGUAL:
        target = phonemize_batch_bilingual
    elif args.phoneme_type == PhonemeType.TEXT:
        target = phonemize_batch_text
    elif args.phoneme_type == PhonemeType.OPENJTALK:
        target = phonemize_batch_openjtalk
    else:
        target = phonemize_batch_espeak

    processes = [
        Process(target=target, args=(args, queue_in, queue_out))
        for _ in range(args.max_workers)
    ]
    for proc in processes:
        proc.start()

    _LOGGER.info(
        "Processing %s utterance(s) with %s worker(s)", num_utterances, args.max_workers
    )
    # プログレスバーを表示（stdoutに表示し、早めに初期化）
    print(
        f"Starting to process {num_utterances} utterances...",
        file=sys.stdout,
        flush=True,
    )
    pbar = tqdm(
        total=num_utterances,
        desc="Preprocessing",
        unit="utt",
        file=sys.stdout,
        leave=True,
        dynamic_ncols=True,
        ascii=True,
        disable=False,
    )

    output_dataset_path = args.output_dir / "dataset.jsonl"
    # 途中で処理が停止してもこれまでの結果を保持できるよう、追加(append)モードで開く
    with open(output_dataset_path, "a", encoding="utf-8") as dataset_file:
        for utt_batch in batched(
            make_dataset(args),
            batch_size,
        ):
            queue_in.put(utt_batch)

        _LOGGER.debug("Waiting for jobs to finish")
        missing_phonemes: Counter[str] = Counter()
        for _ in range(num_utterances):
            utt = queue_out.get()
            if utt is not None:
                if utt.speaker is not None:
                    utt.speaker_id = speaker_ids[utt.speaker]

                utt_dict = dataclasses.asdict(utt)
                utt_dict.pop("missing_phonemes")

                # JSONL
                json.dump(
                    utt_dict,
                    dataset_file,
                    ensure_ascii=True,
                    cls=PathEncoder,
                )
                print("", file=dataset_file)

                missing_phonemes.update(utt.missing_phonemes)

            # プログレスバーを最後に更新（処理済みかどうかに関わらず）
            pbar.update(1)
            if (pbar.n % 500) == 0:
                pbar.refresh()

            # データ損失を防ぐため、定期的にフラッシュする
            if (pbar.n % 100) == 0:
                dataset_file.flush()

        pbar.close()
        if missing_phonemes:
            for phoneme, count in missing_phonemes.most_common():
                _LOGGER.warning("Missing %s (%s)", phoneme, count)

            _LOGGER.warning("Missing %s phoneme(s)", len(missing_phonemes))

    # Signal workers to stop
    for _proc in processes:
        queue_in.put(None)

    # Wait for workers to stop
    for proc in processes:
        proc.join(timeout=1)


# -----------------------------------------------------------------------------


def get_text_casing(casing: str):
    if casing == "lower":
        return str.lower

    if casing == "upper":
        return str.upper

    if casing == "casefold":
        return str.casefold

    return lambda s: s


def _cache_audio(
    args: argparse.Namespace,
    utt: "Utterance",
    silence_detector: "SileroVoiceActivityDetector | None",  # noqa: F821
) -> tuple[Path, Path]:
    """Dispatch audio caching to energy VAD or Silero VAD based on args."""
    if getattr(args, "energy_vad", True):
        return cache_norm_audio_fast(
            utt.audio_path,
            args.cache_dir,
            args.sample_rate,
        )
    else:
        assert silence_detector is not None, (
            "silence_detector must be provided when --no-energy-vad is used"
        )
        return cache_norm_audio(
            utt.audio_path,
            args.cache_dir,
            silence_detector,
            args.sample_rate,
        )


def phonemize_batch_espeak(
    args: argparse.Namespace, queue_in: JoinableQueue, queue_out: Queue
):
    try:
        # Suppress C-level warnings from pyopenjtalk/OpenJTalk to keep output clean
        if not getattr(args, "debug", False):
            devnull_fd = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull_fd, 2)

        casing = get_text_casing(args.text_casing)
        silence_detector = (
            make_silence_detector() if not getattr(args, "energy_vad", True) else None
        )

        # Timeout
        timeout_sec = getattr(args, "timeout_seconds", 0)

        def _timeout_handler(signum, frame):
            raise TimeoutError()

        if timeout_sec > 0 and _HAS_SIGALRM:
            signal.signal(signal.SIGALRM, _timeout_handler)
        elif timeout_sec > 0 and not _HAS_SIGALRM:
            _LOGGER.warning(
                "Timeouts requested (timeout_seconds=%d) but SIGALRM is not available "
                "on this platform; timeouts will not be enforced in this worker.",
                timeout_sec,
            )

        while True:
            utt_batch = queue_in.get()
            if utt_batch is None:
                break

            for utt in utt_batch:
                try:
                    if args.tashkeel:
                        utt.text = tashkeel_run(utt.text)

                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(timeout_sec)
                    _LOGGER.debug(utt)
                    all_phonemes = phonemize_espeak(casing(utt.text), args.language)

                    # Flatten
                    utt.phonemes = [
                        phoneme
                        for sentence_phonemes in all_phonemes
                        for phoneme in sentence_phonemes
                    ]
                    utt.phoneme_ids = phoneme_ids_espeak(
                        utt.phonemes,
                        missing_phonemes=utt.missing_phonemes,
                    )
                    if not args.skip_audio:
                        utt.audio_norm_path, utt.audio_spec_path = _cache_audio(
                            args, utt, silence_detector
                        )
                    queue_out.put(utt)
                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(0)
                except TimeoutError:
                    _LOGGER.error("Skipping utterance due to timeout: %s", utt)
                    queue_out.put(None)
                except Exception:
                    _LOGGER.exception("Failed to process utterance: %s", utt)
                    queue_out.put(None)

            queue_in.task_done()
    except Exception:
        _LOGGER.exception("phonemize_batch_espeak")


def phonemize_batch_text(
    args: argparse.Namespace, queue_in: JoinableQueue, queue_out: Queue
):
    try:
        if not getattr(args, "debug", False):
            devnull_fd = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull_fd, 2)

        casing = get_text_casing(args.text_casing)
        silence_detector = (
            make_silence_detector() if not getattr(args, "energy_vad", True) else None
        )

        timeout_sec = getattr(args, "timeout_seconds", 0)

        def _timeout_handler(signum, frame):
            raise TimeoutError()

        if timeout_sec > 0 and _HAS_SIGALRM:
            signal.signal(signal.SIGALRM, _timeout_handler)
        elif timeout_sec > 0 and not _HAS_SIGALRM:
            _LOGGER.warning(
                "Timeouts requested (timeout_seconds=%d) but SIGALRM is not available "
                "on this platform; timeouts will not be enforced in this worker.",
                timeout_sec,
            )

        while True:
            utt_batch = queue_in.get()
            if utt_batch is None:
                break

            for utt in utt_batch:
                try:
                    if args.tashkeel:
                        utt.text = tashkeel_run(utt.text)

                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(timeout_sec)
                    _LOGGER.debug(utt)
                    all_phonemes = phonemize_codepoints(casing(utt.text))
                    # Flatten
                    utt.phonemes = [
                        phoneme
                        for sentence_phonemes in all_phonemes
                        for phoneme in sentence_phonemes
                    ]
                    utt.phoneme_ids = phoneme_ids_codepoints(
                        args.language,
                        utt.phonemes,
                        missing_phonemes=utt.missing_phonemes,
                    )
                    if not args.skip_audio:
                        utt.audio_norm_path, utt.audio_spec_path = _cache_audio(
                            args, utt, silence_detector
                        )
                    queue_out.put(utt)
                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(0)
                except TimeoutError:
                    _LOGGER.error("Skipping utterance due to timeout: %s", utt)
                    queue_out.put(None)
                except Exception:
                    _LOGGER.exception("Failed to process utterance: %s", utt)
                    queue_out.put(None)

            queue_in.task_done()
    except Exception:
        _LOGGER.exception("phonemize_batch_text")


def phonemize_batch_openjtalk(
    args: argparse.Namespace, queue_in: JoinableQueue, queue_out: Queue
):
    try:
        if not getattr(args, "debug", False):
            devnull_fd = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull_fd, 2)

        casing = get_text_casing(args.text_casing)
        silence_detector = (
            make_silence_detector() if not getattr(args, "energy_vad", True) else None
        )

        # カスタム辞書を読み込む（存在する場合）
        custom_dict = None
        dict_path = (
            Path(__file__).parent.parent.parent.parent
            / "data"
            / "dictionaries"
            / "user_custom_dict.json"
        )
        if dict_path.exists():
            _LOGGER.info(f"Loading custom dictionary from {dict_path}")
            custom_dict = CustomDictionary(str(dict_path))
        else:
            _LOGGER.debug(f"No custom dictionary found at {dict_path}")

        # Create JapanesePhonemizer from piper_plus_g2p (once per worker)
        ja_phonemizer = JapanesePhonemizer(custom_dict=custom_dict)

        timeout_sec = getattr(args, "timeout_seconds", 0)

        def _timeout_handler(signum, frame):
            raise TimeoutError()

        if timeout_sec > 0 and _HAS_SIGALRM:
            signal.signal(signal.SIGALRM, _timeout_handler)
        elif timeout_sec > 0 and not _HAS_SIGALRM:
            _LOGGER.warning(
                "Timeouts requested (timeout_seconds=%d) but SIGALRM is not available "
                "on this platform; timeouts will not be enforced in this worker.",
                timeout_sec,
            )

        while True:
            utt_batch = queue_in.get()
            if utt_batch is None:
                break

            for utt in utt_batch:
                try:
                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(timeout_sec)
                    _LOGGER.debug(utt)
                    # piper_plus_g2p: clean tokens (no BOS, has EOS, no PUA)
                    raw_tokens, prosody_info_list = (
                        ja_phonemizer.phonemize_with_prosody(casing(utt.text))
                    )
                    # Prepend BOS "^" (piper_plus_g2p omits it)
                    raw_tokens = ["^"] + raw_tokens
                    prosody_info_list = [None] + list(prosody_info_list)

                    # Apply PUA mapping and build phoneme_ids
                    utt.phonemes = []
                    utt.phoneme_ids = []
                    for token in raw_tokens:
                        mapped = map_token(token)
                        utt.phonemes.append(mapped)
                        if mapped in args.phoneme_id_map:
                            utt.phoneme_ids.extend(args.phoneme_id_map[mapped])
                        else:
                            utt.missing_phonemes[mapped] += 1
                            _LOGGER.warning(f"Missing phoneme: {mapped}")

                    # prosody_features: A1/A2/A3 値を辞書形式で保存
                    utt.prosody_features = [
                        {"a1": p.a1, "a2": p.a2, "a3": p.a3} if p is not None else None
                        for p in prosody_info_list
                    ]
                    # prosody_ids は将来の拡張用（現在は空）
                    utt.prosody_ids = []

                    # 長さ検証: phoneme_ids と prosody_features の長さが一致することを確認
                    # これが一致しないと学習時にSIGSEGVが発生する可能性がある
                    if len(utt.phoneme_ids) != len(utt.prosody_features):
                        _LOGGER.error(
                            "Length mismatch: phoneme_ids=%d, prosody_features=%d, text='%s'",
                            len(utt.phoneme_ids),
                            len(utt.prosody_features),
                            utt.text[:50],
                        )
                        # 長さを揃える（短い方に合わせる）
                        min_len = min(len(utt.phoneme_ids), len(utt.prosody_features))
                        utt.phoneme_ids = utt.phoneme_ids[:min_len]
                        utt.prosody_features = utt.prosody_features[:min_len]
                        _LOGGER.warning(
                            "Truncated to %d elements to avoid training crash", min_len
                        )

                    if not args.skip_audio:
                        utt.audio_norm_path, utt.audio_spec_path = _cache_audio(
                            args, utt, silence_detector
                        )

                        # Extract F0 if enabled
                        if getattr(args, "extract_f0", False):
                            utt.f0_path = cache_f0(
                                utt.audio_path,
                                args.cache_dir,
                                args.sample_rate,
                                hop_length=args.hop_length,
                                f0_min=getattr(args, "f0_min", 80.0),
                                f0_max=getattr(args, "f0_max", 880.0),
                            )
                    queue_out.put(utt)
                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(0)
                except TimeoutError:
                    _LOGGER.error("Skipping utterance due to timeout: %s", utt)
                    queue_out.put(None)
                except Exception:
                    _LOGGER.exception("Failed to process utterance: %s", utt)
                    queue_out.put(None)

            queue_in.task_done()
    except Exception:
        _LOGGER.exception("phonemize_batch_openjtalk")


def _phonemize_batch_multilingual_impl(
    args: argparse.Namespace,
    queue_in: JoinableQueue,
    queue_out: Queue,
    phonemizer: MultilingualPhonemizer,
    label: str,
):
    """Shared implementation for multilingual/bilingual batch phonemization.

    Parameters
    ----------
    phonemizer : MultilingualPhonemizer
        The phonemizer instance to use for text conversion (from piper_plus_g2p).
    label : str
        Label for error logging (e.g. "multilingual" or "bilingual").
    """
    try:
        if not getattr(args, "debug", False):
            devnull_fd = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull_fd, 2)

        casing = get_text_casing(args.text_casing)
        silence_detector = (
            make_silence_detector() if not getattr(args, "energy_vad", True) else None
        )

        # PiperEncoder handles PUA mapping + BOS/EOS/padding
        encoder = PiperEncoder(args.phoneme_id_map)

        # EOS tokens that JapanesePhonemizer may emit (strip from segments)
        _eos_tokens = frozenset({"$", "?", "?!", "?.", "?~"})

        timeout_sec = getattr(args, "timeout_seconds", 0)

        def _timeout_handler(signum, frame):
            raise TimeoutError()

        if timeout_sec > 0 and _HAS_SIGALRM:
            signal.signal(signal.SIGALRM, _timeout_handler)
        elif timeout_sec > 0 and not _HAS_SIGALRM:
            _LOGGER.warning(
                "Timeouts requested (timeout_seconds=%d) but SIGALRM is not available "
                "on this platform; timeouts will not be enforced in this worker.",
                timeout_sec,
            )

        # Build language_id_map and detector once per worker for multilingual mode
        language_id_map: dict[str, int] = {}
        _lang_detector = None
        if hasattr(args, "lang_parts") and args.lang_parts:
            language_id_map = {lang: idx for idx, lang in enumerate(args.lang_parts)}
            _lang_detector = UnicodeLanguageDetector(
                args.lang_parts,
                default_latin_language="en"
                if "en" in args.lang_parts
                else args.lang_parts[0],
            )
        elif getattr(args, "phoneme_type", None) == PhonemeType.BILINGUAL:
            language_id_map = {"ja": 0, "en": 1}
            _lang_detector = UnicodeLanguageDetector(
                ["ja", "en"],
                default_latin_language="en",
            )

        while True:
            utt_batch = queue_in.get()
            if utt_batch is None:
                break

            for utt in utt_batch:
                try:
                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(timeout_sec)
                    _LOGGER.debug(utt)
                    text = casing(utt.text)

                    # piper_plus_g2p: clean tokens (no BOS, no PUA mapping)
                    # JA segments may include EOS markers ("$", "?" etc.)
                    raw_tokens, raw_prosody = phonemizer.phonemize_with_prosody(text)

                    # Strip EOS markers from segments, tracking the last one
                    # (piper_plus_g2p MultilingualPhonemizer does not strip them)
                    clean_tokens = []
                    clean_prosody = []
                    last_eos = "$"
                    for tok, pro in zip(raw_tokens, raw_prosody, strict=True):
                        if tok in _eos_tokens:
                            last_eos = tok
                            continue
                        clean_tokens.append(tok)
                        clean_prosody.append(pro)

                    # PiperEncoder: PUA map -> phoneme_ids -> BOS/EOS/padding
                    utt.phoneme_ids, prosody_out = encoder.encode_with_prosody(
                        clean_tokens, clean_prosody, eos_token=last_eos
                    )
                    utt.phonemes = clean_tokens
                    utt.prosody_features = PiperEncoder.prosody_to_dicts(prosody_out)
                    utt.prosody_ids = []

                    # Detect and set language_id for multilingual/bilingual utterances
                    if _lang_detector is not None and language_id_map:
                        context_has_kana = _lang_detector.has_kana(utt.text)
                        counts: dict[str, int] = {}
                        for ch in utt.text:
                            lang = _lang_detector.detect_char(
                                ch, context_has_kana=context_has_kana
                            )
                            if lang is not None:
                                counts[lang] = counts.get(lang, 0) + 1
                        if counts:
                            dominant = max(counts, key=lambda k: counts[k])
                            utt.language_id = language_id_map.get(dominant, 0)
                        else:
                            utt.language_id = 0

                    # Length validation
                    if len(utt.phoneme_ids) != len(utt.prosody_features):
                        _LOGGER.error(
                            "Length mismatch: phoneme_ids=%d, prosody_features=%d",
                            len(utt.phoneme_ids),
                            len(utt.prosody_features),
                        )
                        min_len = min(len(utt.phoneme_ids), len(utt.prosody_features))
                        utt.phoneme_ids = utt.phoneme_ids[:min_len]
                        utt.prosody_features = utt.prosody_features[:min_len]

                    if not args.skip_audio:
                        utt.audio_norm_path, utt.audio_spec_path = _cache_audio(
                            args, utt, silence_detector
                        )

                        if getattr(args, "extract_f0", False):
                            utt.f0_path = cache_f0(
                                utt.audio_path,
                                args.cache_dir,
                                args.sample_rate,
                                hop_length=args.hop_length,
                                f0_min=getattr(args, "f0_min", 80.0),
                                f0_max=getattr(args, "f0_max", 880.0),
                            )
                    queue_out.put(utt)
                    if timeout_sec > 0 and _HAS_SIGALRM:
                        signal.alarm(0)
                except TimeoutError:
                    _LOGGER.error("Skipping utterance due to timeout: %s", utt)
                    queue_out.put(None)
                except Exception:
                    _LOGGER.exception("Failed to process utterance: %s", utt)
                    queue_out.put(None)

            queue_in.task_done()
    except Exception:
        _LOGGER.exception("phonemize_batch_%s", label)


def phonemize_batch_multilingual(
    args: argparse.Namespace, queue_in: JoinableQueue, queue_out: Queue
):
    """Multilingual (N languages) phonemization using piper_plus_g2p MultilingualPhonemizer."""
    lang_parts = getattr(args, "lang_parts", args.language.split("-"))
    phonemizer = MultilingualPhonemizer(lang_parts)
    _phonemize_batch_multilingual_impl(
        args, queue_in, queue_out, phonemizer, "multilingual"
    )


def phonemize_batch_bilingual(
    args: argparse.Namespace, queue_in: JoinableQueue, queue_out: Queue
):
    """Bilingual (JA+EN) phonemization using piper_plus_g2p MultilingualPhonemizer.

    Uses MultilingualPhonemizer with ["ja", "en"] language list.
    """
    phonemizer = MultilingualPhonemizer(["ja", "en"])
    _phonemize_batch_multilingual_impl(
        args, queue_in, queue_out, phonemizer, "bilingual"
    )


# -----------------------------------------------------------------------------


@dataclass
class Utterance:
    text: str
    audio_path: Path
    speaker: str | None = None
    speaker_id: int | None = None
    language_id: int | None = None
    phonemes: list[str] | None = None
    phoneme_ids: list[int] | None = None
    prosody_ids: list[int] | None = None
    prosody_features: list[dict | None] | None = None  # A1/A2/A3 per phoneme
    audio_norm_path: Path | None = None
    audio_spec_path: Path | None = None
    f0_path: Path | None = None  # Path to cached F0 values
    missing_phonemes: "Counter[str]" = field(default_factory=Counter)


class PathEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Path):
            return str(o)
        return super().default(o)


def ljspeech_dataset(args: argparse.Namespace) -> Iterable[Utterance]:
    dataset_dir = args.input_dir
    is_single_speaker = args.single_speaker
    speaker_id = args.speaker_id
    skip_audio = args.skip_audio

    # filename|speaker|text
    # speaker is optional
    metadata_path = dataset_dir / "metadata.csv"
    assert metadata_path.exists(), f"Missing {metadata_path}"

    wav_dir = dataset_dir / "wav"
    if not wav_dir.is_dir():
        wav_dir = dataset_dir / "wavs"

    with open(metadata_path, encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file, delimiter="|")
        for row in reader:
            assert len(row) >= 2, "Not enough columns"

            speaker: str | None = None
            if is_single_speaker or (len(row) == 2):
                filename, text = row[0], row[-1]
            else:
                filename, speaker, text = row[0], row[1], row[-1]

            # Try file name relative to metadata
            wav_path = metadata_path.parent / filename

            if not wav_path.exists():
                # Try with .wav
                wav_path = metadata_path.parent / f"{filename}.wav"

            if not wav_path.exists():
                # Try wav/ or wavs/
                wav_path = wav_dir / filename

            if not wav_path.exists():
                # Try with .wav
                wav_path = wav_dir / f"{filename}.wav"

            if not skip_audio:
                if not wav_path.exists():
                    _LOGGER.warning("Missing %s", filename)
                    continue

                if wav_path.stat().st_size == 0:
                    _LOGGER.warning("Empty file: %s", wav_path)
                    continue

            yield Utterance(
                text=text, audio_path=wav_path, speaker=speaker, speaker_id=speaker_id
            )


def mycroft_dataset(args: argparse.Namespace) -> Iterable[Utterance]:
    dataset_dir = args.input_dir
    is_single_speaker = args.single_speaker
    skip_audio = args.skip_audio

    speaker_id = 0
    for metadata_path in dataset_dir.glob("**/*-metadata.txt"):
        speaker = metadata_path.parent.name if not is_single_speaker else None
        with open(metadata_path, encoding="utf-8") as csv_file:
            # filename|text|length
            reader = csv.reader(csv_file, delimiter="|")
            for row in reader:
                filename, text = row[0], row[1]
                wav_path = metadata_path.parent / filename
                if skip_audio or (wav_path.exists() and (wav_path.stat().st_size > 0)):
                    yield Utterance(
                        text=text,
                        audio_path=wav_path,
                        speaker=speaker,
                        speaker_id=speaker_id if not is_single_speaker else None,
                    )
        speaker_id += 1


# -----------------------------------------------------------------------------


def batched(iterable, n):
    "Batch data into lists of length n. The last batch may be shorter."
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    it = iter(iterable)
    batch = list(itertools.islice(it, n))
    while batch:
        yield batch
        batch = list(itertools.islice(it, n))


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
