"""Unit tests for scripts/verify_rekor_releases.py (T-001)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_rekor_releases.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "rekor-verify"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "verify_rekor_releases",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rekor():
    return _load_module()


def test_certificate_identity_mirrors_pr_511(rekor):
    """The verify side MUST mirror the signing side byte-for-byte (M1-R3).

    If this assertion fails, PR #511's cosign-release-artifacts.yml has
    drifted from the verify script — investigate and resync before
    trusting any verify result.
    """
    cosign_yml = (
        REPO_ROOT / ".github" / "workflows" / "cosign-release-artifacts.yml"
    ).read_text(encoding="utf-8")
    assert rekor.CERTIFICATE_IDENTITY_REGEXP in cosign_yml, (
        f"verify side identity-regexp {rekor.CERTIFICATE_IDENTITY_REGEXP!r} "
        "not found in PR #511's signing workflow — drift detected."
    )
    assert rekor.CERTIFICATE_OIDC_ISSUER in cosign_yml, (
        f"verify side oidc-issuer {rekor.CERTIFICATE_OIDC_ISSUER!r} "
        "not found in PR #511's signing workflow — drift detected."
    )


def test_find_assets_pairs_sig_and_pem(rekor):
    release = {
        "tag": "v1.13.0",
        "assets": [
            {"name": "foo.tar.gz"},
            {"name": "foo.tar.gz.sig"},
            {"name": "foo.tar.gz.pem"},
        ],
    }
    artifacts = rekor.find_assets_for_release(release)
    assert artifacts == [
        {
            "name": "foo.tar.gz",
            "sig": "foo.tar.gz.sig",
            "pem": "foo.tar.gz.pem",
            "expected_verify": "pass",
        }
    ]


def test_find_assets_preserves_expected_verify_meta(rekor):
    release = {
        "tag": "v1.0.0",
        "assets": [
            {"name": "bad.zip", "expected_verify": "fail"},
            {"name": "bad.zip.sig"},
            {"name": "bad.zip.pem"},
        ],
    }
    [artifact] = rekor.find_assets_for_release(release)
    assert artifact["expected_verify"] == "fail"


def test_classify_asset_ready_when_sig_and_pem_present(rekor):
    assert (
        rekor.classify_asset(
            {
                "name": "x.tar.gz",
                "sig": "x.tar.gz.sig",
                "pem": "x.tar.gz.pem",
                "expected_verify": "pass",
            }
        )
        == "ready"
    )


def test_classify_asset_skipped_when_legacy(rekor):
    # Legacy release: artifact present, .sig / .pem missing.
    assert (
        rekor.classify_asset(
            {
                "name": "old.tar.gz",
                "sig": "",
                "pem": "",
                "expected_verify": "pass",
            }
        )
        == "skipped"
    )


def test_run_verify_returns_pass_for_golden(rekor, tmp_path: Path):
    releases = json.loads(
        (FIXTURES / "golden_release.json").read_text(encoding="utf-8"),
    )["releases"]
    results = rekor.run_verify(releases, tmp_path)
    statuses = [r["status"] for r in results]
    # 2 artifacts × 1 release, both pass
    assert statuses == ["pass", "pass"]


def test_run_verify_returns_skipped_for_legacy(rekor, tmp_path: Path):
    releases = json.loads(
        (FIXTURES / "legacy_release.json").read_text(encoding="utf-8"),
    )["releases"]
    results = rekor.run_verify(releases, tmp_path)
    assert all(r["status"] == "skipped" for r in results)


def test_run_verify_uses_download_fn_when_provided(rekor, tmp_path: Path):
    releases = [
        {
            "tag": "v1.13.0",
            "assets": [
                {"name": "foo.tar.gz"},
                {"name": "foo.tar.gz.sig"},
                {"name": "foo.tar.gz.pem"},
            ],
        }
    ]

    download_calls: list[tuple[str, str]] = []

    def fake_download(tag: str, asset: str, dest: Path) -> Path:
        download_calls.append((tag, asset))
        target = dest / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"dummy")
        return target

    cosign_calls: list[list[str]] = []

    def fake_cosign(argv: list[str]) -> int:
        cosign_calls.append(argv)
        return 0

    results = rekor.run_verify(
        releases,
        tmp_path,
        cosign_runner=fake_cosign,
        download_fn=fake_download,
    )
    assert results[0]["status"] == "pass"
    assert len(download_calls) == 3  # artifact + sig + pem
    assert len(cosign_calls) == 1
    cmd = cosign_calls[0]
    assert "--certificate-identity-regexp" in cmd
    idx = cmd.index("--certificate-identity-regexp")
    assert cmd[idx + 1] == rekor.CERTIFICATE_IDENTITY_REGEXP
    assert "--rekor-url" in cmd


def test_run_verify_returns_fail_when_cosign_nonzero(
    rekor,
    tmp_path: Path,
):
    releases = [
        {
            "tag": "v1.13.0",
            "assets": [
                {"name": "foo.tar.gz"},
                {"name": "foo.tar.gz.sig"},
                {"name": "foo.tar.gz.pem"},
            ],
        }
    ]

    def fake_download(tag, asset, dest):
        target = dest / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"dummy")
        return target

    def fake_cosign_fail(argv):
        return 1

    results = rekor.run_verify(
        releases,
        tmp_path,
        cosign_runner=fake_cosign_fail,
        download_fn=fake_download,
    )
    assert results[0]["status"] == "fail"
    assert "exit 1" in results[0]["error"]


def test_main_silent_zero_warning_on_empty_release_list(
    rekor,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    fixture = tmp_path / "empty.json"
    fixture.write_text(json.dumps({"releases": []}))
    rc = rekor.main(["--fixture", str(fixture)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Collected releases (0)" in captured.err
    assert "::warning::" in captured.err


def test_main_returns_zero_for_golden_fixture(
    rekor,
    capsys: pytest.CaptureFixture,
):
    rc = rekor.main(
        [
            "--fixture",
            str(FIXTURES / "golden_release.json"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "**PASS**" in captured.out
    assert "Summary: total=2, pass=2" in captured.out


def test_main_returns_zero_for_legacy_fixture(
    rekor,
    capsys: pytest.CaptureFixture,
):
    rc = rekor.main(
        [
            "--fixture",
            str(FIXTURES / "legacy_release.json"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0  # skipped only → exit 0
    assert "**SKIPPED**" in captured.out


def test_main_emits_collected_log_always(
    rekor,
    capsys: pytest.CaptureFixture,
):
    rekor.main(["--fixture", str(FIXTURES / "golden_release.json")])
    captured = capsys.readouterr()
    assert "Collected releases (1): v1.13.0" in captured.err


def test_verify_blob_returns_error_on_missing_cosign(rekor, tmp_path: Path):
    def runner_raises(argv):
        raise FileNotFoundError(argv[0])

    result = rekor.verify_blob(
        artifact_path=tmp_path / "a.tar.gz",
        sig_path=tmp_path / "a.tar.gz.sig",
        pem_path=tmp_path / "a.tar.gz.pem",
        runner=runner_raises,
    )
    assert result["status"] == "error"
    assert "cosign binary not found" in result["error"]


def test_load_fixture_rejects_bad_shape(rekor, tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"foo": "bar"}')
    with pytest.raises(ValueError, match="'releases'"):
        rekor.load_fixture(bad)
