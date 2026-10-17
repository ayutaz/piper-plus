"""Run the pinned CPU evaluator with verified read-only reuse of repeated work.

Generation sources and metric definitions are unchanged. Full SHA256 hashes are
read once per unchanged file and again at completion; real acoustic analysis is
reused only for the same ordered content hashes. No GPU/training calls occur.
"""

import copy
import json
import os
import sys
from pathlib import Path


class HashCache:
    def __init__(self, reader):
        self.reader = reader
        self.entries = {}
        self.hits = 0

    @staticmethod
    def identity(path):
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)

    def __call__(self, value):
        path = Path(value).resolve()
        before = self.identity(path)
        previous = self.entries.get(path)
        if previous is not None and before == previous[0]:
            self.hits += 1
            return previous[1]
        digest = self.reader(path)
        if self.identity(path) != before:
            raise ValueError(f"input changed while hashing: {path}")
        self.entries[path] = (before, digest)
        return digest

    def verify_all(self):
        """Re-read every hash, even if a mutation preserved filesystem metadata."""
        for path, (_, expected) in self.entries.items():
            if self.reader(path) != expected:
                raise ValueError(f"input changed during evaluation: {path}")


def main(argv=None):
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    from piper_train import embedding_cache, evaluation_manifest  # noqa: PLC0415
    from piper_train.tools import (  # noqa: PLC0415
        eval_cer,
        eval_zs_secs,
        prepare_zero_shot_cpu,
    )

    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--stage" in arguments:
        raise ValueError("this runner exclusively performs the evaluate stage")
    output = Path(arguments[arguments.index("--output") + 1]).resolve()
    original_hash = embedding_cache.file_sha256
    cache = HashCache(original_hash)
    for module in (
        embedding_cache,
        evaluation_manifest,
        eval_cer,
        prepare_zero_shot_cpu,
    ):
        module.file_sha256 = cache
    original_analysis = eval_zs_secs._analyze_clip_group
    analyses = {}
    analysis_hits = 0

    def analyze(paths):
        nonlocal analysis_hits
        key = tuple((str(Path(path).resolve()), cache(path)) for path in paths)
        if key not in analyses:
            analyses[key] = original_analysis(paths)
        else:
            analysis_hits += 1
        return copy.deepcopy(analyses[key])

    eval_zs_secs._analyze_clip_group = analyze
    original_factory = eval_cer.build_whisper_transcribe_fn

    def factory(*args, **kwargs):
        transcribe = original_factory(*args, **kwargs)

        def logged(path):
            print(f"ASR_BEGIN {path}", flush=True)
            text = transcribe(path)
            print(f"ASR_DONE {path.name}", flush=True)
            return text

        return logged

    eval_cer.build_whisper_transcribe_fn = factory
    result = prepare_zero_shot_cpu.main([*arguments, "--stage", "evaluate"])
    print("FINAL_UNCACHED_HASH_CHECK_BEGIN", flush=True)
    cache.verify_all()
    report = {
        "status": "VERIFIED",
        "driver": {
            "path": str(Path(__file__).resolve()),
            "sha256": original_hash(Path(__file__)),
        },
        "baseline_sha256": original_hash(output / "baseline.json"),
        "hashes_rechecked_without_cache": len(cache.entries),
        "hash_cache_hits": cache.hits,
        "acoustic_group_reuse_count": analysis_hits,
        "policy": "same metric definitions; full final hash re-read; CPU only; no ASR decoding changes",
    }
    prepare_zero_shot_cpu.write_json(output / "evaluation-execution.json", report)
    print(json.dumps(report), flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
