"""Run the same lightweight release regression suite in CI and pre-commit."""

import subprocess
import sys
from pathlib import Path


TESTS = [
    "tests/scripts/test_prepare_release_draft.py",
    "tests/scripts/test_release_regression_guards.py",
    "tests/scripts/test_docker_release_tags.py",
    "tests/scripts/test_docker_signature_recovery.py",
]


if __name__ == "__main__":
    sys.exit(
        subprocess.run(
            [sys.executable, "-m", "pytest", *TESTS, "-q", "-o", "addopts="],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
        ).returncode
    )
