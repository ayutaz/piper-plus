"""Build sdists/wheels and run an isolated installed-wheel consumer (uv required)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT) -> None:
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--with-model", action="store_true")
    args = parser.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    env = work / "env"
    if env.exists():
        raise FileExistsError(f"Use a fresh consumer directory: {env}")
    run(sys.executable, ROOT / "scripts/check_bundled_english.py")
    wheels = work / "wheels"
    for package in ("piper-plus", "piper-plus-g2p"):
        # uv builds the wheel FROM the sdist by default, exercising both payloads.
        run("uv", "build", "--package", package, "--out-dir", wheels)
    runtime = next(wheels.glob("piper_plus-*.whl"))
    g2p = next(wheels.glob("piper_plus_g2p-*.whl"))
    g2p_version = tomllib.loads(
        (ROOT / "src/python/g2p/pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    for wheel, name, version in (
        (runtime, "piper-plus", (ROOT / "VERSION").read_text().strip()),
        (g2p, "piper-plus-g2p", g2p_version),
    ):
        run(
            sys.executable,
            ROOT / "scripts/check_python_release_wheel.py",
            "--name",
            name,
            "--version",
            version,
            wheel,
        )
    run("uv", "venv", "--python", sys.executable, env)
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        "uv",
        "pip",
        "install",
        "--python",
        python,
        f"{runtime}[cpu,http]",
        f"{g2p}[all]",
        "packaging",
    )
    run("uv", "pip", "check", "--python", python)
    run(
        python,
        "-I",
        ROOT / "scripts/check_python_licenses.py",
        "--root",
        "piper-plus[cpu,http]",
        "--root",
        "piper-plus-g2p[all]",
        "--report",
        work / "licenses.json",
        cwd=work,
    )
    command = [
        python,
        "-I",
        ROOT / "scripts/check_english_consumer.py",
        "--fixture",
        ROOT / "tests/fixtures/english_g2p_compat.json",
        "--output",
        work / "evidence",
    ]
    if args.with_model:
        command.extend(
            ["--public-base-manifest", ROOT / "docs/spec/model-sha256-manifest.toml"]
        )
    run(*command, cwd=work)


if __name__ == "__main__":
    main()
