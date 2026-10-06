"""Exercise installed native notices without compiling the runtime."""

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def layout(tmp_path):
    files = [
        "include/piper_plus.h",
        "lib/pkgconfig/piper_plus.pc",
        "lib/cmake/PiperPlus/PiperPlusConfig.cmake",
        "lib/cmake/PiperPlus/PiperPlusTargets.cmake",
        "lib/cmake/PiperPlus/PiperPlusConfigVersion.cmake",
        "bin/piper_plus.dll",
        "lib/piper_plus.lib",
        "lib/libpiper_plus.so",
        "lib/libpiper_plus.so.1",
        "lib/libpiper_plus.dylib",
        "bin/onnxruntime.dll",
        "lib/libonnxruntime.so",
        "lib/libonnxruntime.dylib",
        "share/piper-plus/dicts/cmudict_data.json",
        "share/licenses/piper-plus/LICENSE.md",
        "share/licenses/onnxruntime/LICENSE",
    ]
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture", encoding="utf-8")
    return tmp_path


def test_complete_native_layout_is_accepted(tmp_path):
    subprocess.run(
        [
            "cmake",
            f"-DPREFIX={layout(tmp_path)}",
            "-P",
            str(ROOT / "cmake/verify_install_layout.cmake"),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "missing",
    ["share/licenses/piper-plus/LICENSE.md", "share/licenses/onnxruntime/LICENSE"],
)
def test_native_layout_requires_license_text(tmp_path, missing):
    prefix = layout(tmp_path)
    (prefix / missing).unlink()
    result = subprocess.run(
        [
            "cmake",
            f"-DPREFIX={prefix}",
            "-P",
            str(ROOT / "cmake/verify_install_layout.cmake"),
        ],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode != 0
    assert "LICENSE" in result.stdout + result.stderr


@pytest.mark.parametrize("sdk_path", ["sdk", "ort_dl/src/onnxruntime_external"])
def test_ort_notices_are_resolved_at_install_time(tmp_path, sdk_path):
    sdk = tmp_path / sdk_path
    prefix = tmp_path / "install"
    runner = tmp_path / "configure.cmake"
    script = tmp_path / "install-notices.cmake"
    runner.write_text(
        f'set(PIPER_ORT_ROOTS "{sdk.as_posix()}")\n'
        'set(CMAKE_INSTALL_DATADIR "share")\n'
        f'configure_file("{(ROOT / "cmake/InstallOrtNotices.cmake.in").as_posix()}" '
        f'"{script.as_posix()}" @ONLY)\n',
        encoding="utf-8",
    )
    subprocess.run(["cmake", "-P", str(runner)], check=True, capture_output=True)
    # ExternalProject downloads the SDK after CMake configuration.
    sdk.mkdir(parents=True)
    (sdk / "LICENSE").write_text("ORT license fixture", encoding="utf-8")
    (sdk / "ThirdPartyNotices.txt").write_text(
        "ORT third party fixture", encoding="utf-8"
    )
    subprocess.run(
        ["cmake", f"-DCMAKE_INSTALL_PREFIX={prefix}", "-P", str(script)],
        check=True,
        capture_output=True,
    )
    notices = prefix / "share/licenses/onnxruntime"
    assert (notices / "LICENSE").read_text() == "ORT license fixture"
    assert (notices / "ThirdPartyNotices.txt").read_text() == "ORT third party fixture"


def test_missing_ort_license_fails_install(tmp_path):
    runner = tmp_path / "run.cmake"
    script = tmp_path / "install-notices.cmake"
    runner.write_text(
        f'set(PIPER_ORT_ROOTS "{(tmp_path / "missing-sdk").as_posix()}")\n'
        'set(CMAKE_INSTALL_DATADIR "share")\n'
        f'configure_file("{(ROOT / "cmake/InstallOrtNotices.cmake.in").as_posix()}" '
        f'"{script.as_posix()}" @ONLY)\n'
        f'include("{script.as_posix()}")\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["cmake", "-P", str(runner)], capture_output=True, encoding="utf-8", check=False
    )
    assert result.returncode != 0
    assert "ONNX Runtime LICENSE" in result.stdout + result.stderr

@pytest.mark.parametrize("notice", ["LICENSE.md", "src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md"])
def test_docker_context_preserves_installed_notices(tmp_path, notice):
    # These basename globs and exact exceptions have the same matching rules
    # in Git and Docker. Exercise the actual ignore file without a Docker daemon.
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(
        (ROOT / ".dockerignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    target = tmp_path / notice
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("notice fixture", encoding="utf-8")
    result = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "--no-index", notice],
        capture_output=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 1, f"Docker context excludes {notice}: {result.stdout}"
