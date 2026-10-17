"""Make the Space modules and the repository sources importable in tests.

The deploy workflow copies these trees next to ``app.py``; tests import the
same sources straight from the repository instead.
"""

import sys
from pathlib import Path


SPACE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SPACE_DIR.parent

for path in (
    REPO_ROOT,
    REPO_ROOT / "src" / "python",
    REPO_ROOT / "src" / "python" / "g2p",
    REPO_ROOT / "src" / "python_run",
    SPACE_DIR,
):
    sys.path.insert(0, str(path))
