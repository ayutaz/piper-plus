"""Repeated CPU evaluation must not conceal input mutation."""

import hashlib
import importlib.util
from pathlib import Path

import pytest


_PATH = Path(__file__).resolve().parents[2] / "scripts/run_zero_shot_cpu_evaluation.py"
_SPEC = importlib.util.spec_from_file_location("cpu_evaluation_driver", _PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_reuse_rechecks_all_hashes_and_detects_changes(tmp_path):
    path = tmp_path / "input"
    path.write_bytes(b"old")
    reads = []

    def reader(value):
        reads.append(value)
        return hashlib.sha256(value.read_bytes()).hexdigest()

    cache = _MODULE.HashCache(reader)
    first = cache(path)
    assert cache(path) == first
    assert len(reads) == 1
    cache.verify_all()
    assert len(reads) == 2
    path.write_bytes(b"new content")
    with pytest.raises(ValueError, match="changed during evaluation"):
        cache.verify_all()
    assert cache(path) != first


def test_mutation_during_hashing_is_rejected(tmp_path):
    path = tmp_path / "input"
    path.write_bytes(b"old")

    def mutating_reader(value):
        digest = hashlib.sha256(value.read_bytes()).hexdigest()
        value.write_bytes(b"changed during read")
        return digest

    with pytest.raises(ValueError, match="changed while hashing"):
        _MODULE.HashCache(mutating_reader)(path)
