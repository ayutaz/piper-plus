"""Reject the x64 SDK that previously reached the ARMv7 linker."""

import hashlib
import io
import json
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def check_sdk(tmp_path, header):
    sdk = tmp_path / "sdk"
    library = sdk / "lib/libonnxruntime.so"
    library.parent.mkdir(parents=True)
    if header is not None:
        library.write_bytes(header)
    runner = tmp_path / "check.cmake"
    runner.write_text(
        f'include("{(ROOT / "cmake/OnnxRuntimeArmv7.cmake").as_posix()}")\n'
        f'piper_check_linux_armv7_ort("{sdk.as_posix()}")\n',
        encoding="utf-8",
    )
    return subprocess.run(
        ["cmake", "-P", str(runner)],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def elf_header(bits=1, machine=40, endian=1):
    data = bytearray(20)
    data[:7] = b"\x7fELF" + bytes([bits, endian, 1])
    data[18:20] = machine.to_bytes(2, "little" if endian == 1 else "big")
    return data


@pytest.mark.parametrize("endian", [1, 2])
def test_arm32_sdk_is_accepted(tmp_path, endian):
    result = check_sdk(tmp_path, elf_header(endian=endian))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "header",
    [None, b"", b"not an ELF library", elf_header(2, 62), elf_header(1, 3)],
)
def test_missing_or_wrong_architecture_sdk_is_rejected(tmp_path, header):
    result = check_sdk(tmp_path, header)
    assert result.returncode != 0
    assert "ARMv7" in result.stderr


def test_cmake_checks_armv7_before_prebuilt_download():
    text = (ROOT / "cmake/OnnxRuntime.cmake").read_text(encoding="utf-8")
    assert text.index("piper_check_linux_armv7_ort") < text.index("ExternalProject_Add")
    assert 'CMAKE_SYSTEM_NAME STREQUAL "Linux"' in text


def test_armv7_release_build_uses_source_sdk_and_real_runtime():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/build-linux-armv7.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["build"]["steps"]
    source = next(
        s for s in steps if s.get("name") == "Build pinned ARMv7 ONNX Runtime"
    )
    assert "scripts/build_ort_armv7.sh" in source["run"]
    native = next(s for s in steps if s.get("name") == "Build in Docker")["run"]
    assert "bash -euo pipefail" in native
    assert "-DONNXRUNTIME_DIR=/workspace/ort-armv7" in native
    assert "cmake --install build" in native
    assert "piper-plus --version" in native
    assert "--output_file" in native
    assert native.index("--output_file") < native.index("tar czf")
    caller = yaml.safe_load(
        (ROOT / ".github/workflows/dev-build-all.yml").read_text(encoding="utf-8")
    )["jobs"]["build_linux_armv7"]
    assert caller["uses"] == "./.github/workflows/build-linux-armv7.yml"
    save = next(s for s in steps if s.get("uses") == "actions/cache/save@v4.3.0")
    restore = next(s for s in steps if s.get("id") == "sdk-cache")
    assert save["with"] == restore["with"]
    fetch = next(s for s in steps if s.get("name") == "Fetch pinned synthesis model")
    assert steps.index(source) < steps.index(save) < steps.index(fetch)


def test_armv7_source_build_is_pinned_and_cross_compiles():
    script = (ROOT / "scripts/build_ort_armv7.sh").read_text(encoding="utf-8")
    assert "c4fb724e810bb496165b9015c77f402727392933" in script
    assert "--arm" in script
    assert "--build_shared_lib" in script
    assert "CMAKE_TOOLCHAIN_FILE=" in script
    assert "--skip_tests" in script
    assert "ThirdPartyNotices.txt" in script
    toolchain = (ROOT / "cmake/linux-armv7-toolchain.cmake").read_text(encoding="utf-8")
    assert "arm-linux-gnueabihf-gcc" in toolchain
    assert "arm-linux-gnueabihf-g++" in toolchain
    assert "-mfpu=neon" in toolchain


def test_armv7_regression_tests_are_required_on_every_pr():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["release-contract"]["steps"]
    assert any("test_armv7_release.py" in s.get("run", "") for s in steps)


def test_eigen_uses_verified_upstream_dependency_commit():
    script = (ROOT / "scripts/build_ort_armv7.sh").read_text(encoding="utf-8")
    assert "--use_preinstalled_eigen" in script
    assert "--eigen_path" in script
    assert "$work/cmake/deps.txt" in script
    assert 'git -C "$work/eigen" fetch --depth 1 origin "$eigen_commit"' in script
    assert 'test "$(git -C "$work/eigen" rev-parse HEAD)" = "$eigen_commit"' in script


def test_model_fetch_uses_published_config_and_verifies_bytes(tmp_path, monkeypatch):
    """Execute the CI downloader against the published model file layout."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/build-linux-armv7.yml").read_text(encoding="utf-8")
    )
    code = next(
        s["run"]
        for s in workflow["jobs"]["build"]["steps"]
        if s.get("name") == "Fetch pinned synthesis model"
    )
    payloads = {"voice.onnx": b"onnx model", "config.json": b'{"sample_rate":22050}'}
    manifest = tmp_path / "src/wasm/openjtalk-web/test/browser/models.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            [
                {
                    "key": "tsukuyomi",
                    "repo": "test/voice",
                    "revision": "pinned-commit",
                    "onnx": "voice.onnx",
                    "onnxSha256": hashlib.sha256(payloads["voice.onnx"]).hexdigest(),
                    "configSha256": hashlib.sha256(payloads["config.json"]).hexdigest(),
                }
            ]
        ),
        encoding="utf-8",
    )
    requests = []

    def fetch(url, timeout):
        requests.append(url)
        base = "https://huggingface.co/test/voice/resolve/pinned-commit/"
        assert url.startswith(base)
        return io.BytesIO(payloads[url.removeprefix(base)])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", fetch)
    exec(compile(code, "ARMv7 model fetch", "exec"), {})
    assert len(requests) == 2
    assert (tmp_path / "armv7-smoke/model.onnx").read_bytes() == payloads["voice.onnx"]
    assert (tmp_path / "armv7-smoke/model.onnx.json").read_bytes() == payloads[
        "config.json"
    ]
    payloads["config.json"] = b"tampered config"
    with pytest.raises(AssertionError):
        exec(compile(code, "ARMv7 model fetch", "exec"), {})
