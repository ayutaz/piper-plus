"""Run the Swift dependency/public consumer regressions in CI and commit hooks."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    sys.exit(
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(ROOT / "tests" / "scripts" / "test_swift_release_consumer.py"),
                "-q",
                "-o",
                "addopts=",
            ],
            cwd=ROOT,
            check=False,
        ).returncode
    )
