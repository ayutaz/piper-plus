#!/usr/bin/env python3
import argparse
import json
import logging
import statistics
import sys
import time

import numpy as np
import onnxruntime

from piper_train.ort_utils import create_session_options


_NOISE_SCALE = 0.667
_LENGTH_SCALE = 1.0
_NOISE_W = 0.8

_LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-m", "--model", required=True, help="Path to Onnx model file (.onnx)"
    )
    parser.add_argument("-c", "--config", help="Path to model config file (.json)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG)

    if not args.config:
        args.config = f"{args.model}.json"

    with open(args.config, encoding="utf-8") as config_file:
        config = json.load(config_file)

    sample_rate = config["audio"]["sample_rate"]
    utterances = [json.loads(line) for line in sys.stdin]

    start_time = time.monotonic_ns()

    session_options = create_session_options()

    session = onnxruntime.InferenceSession(
        args.model,
        sess_options=session_options,
    )

    end_time = time.monotonic_ns()

    load_sec = (end_time - start_time) / 1e9
    synthesize_rtf = []
    for utterance in utterances:
        phoneme_ids = utterance["phoneme_ids"]
        speaker_id = utterance.get("speaker_id")
        synthesize_rtf.append(
            synthesize(
                session,
                phoneme_ids,
                speaker_id,
                sample_rate,
            )
        )

    json.dump(
        {
            "load_sec": load_sec,
            "rtf_mean": statistics.mean(synthesize_rtf),
            "rtf_stdev": statistics.stdev(synthesize_rtf),
            "rtfs": synthesize_rtf,
        },
        sys.stdout,
    )


def synthesize(session, phoneme_ids, speaker_id, sample_rate) -> float:
    phoneme_ids_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
    phoneme_ids_lengths = np.array([phoneme_ids_array.shape[1]], dtype=np.int64)
    scales = np.array(
        [_NOISE_SCALE, _LENGTH_SCALE, _NOISE_W],
        dtype=np.float32,
    )

    sid = None

    if speaker_id is not None:
        sid = np.array([speaker_id], dtype=np.int64)

    # Synthesize through Onnx
    start_time = time.monotonic_ns()
    audio = session.run(
        None,
        {
            "input": phoneme_ids_array,
            "input_lengths": phoneme_ids_lengths,
            "scales": scales,
            "sid": sid,
        },
    )[0].squeeze()
    end_time = time.monotonic_ns()

    audio_sec = len(audio) / sample_rate
    infer_sec = (end_time - start_time) / 1e9
    rtf = infer_sec / audio_sec

    _LOGGER.debug(
        "Real-time factor: %s (infer=%s sec, audio=%s sec)",
        rtf,
        infer_sec,
        audio_sec,
    )

    return rtf


if __name__ == "__main__":
    main()
