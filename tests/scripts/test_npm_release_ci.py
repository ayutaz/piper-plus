"""The exact packed distribution must pass before npm publication and on PRs."""

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_publish_checks_exact_tarball_before_attestation_and_upload():
    steps = workflow("npm-publish.yml")["jobs"]["publish"]["steps"]
    pack = next(i for i, s in enumerate(steps) if s.get("run") == "npm pack")
    verify = next(
        i
        for i, s in enumerate(steps)
        if "npm run test:distribution -- *.tgz" in s.get("run", "")
    )
    attest = next(
        i for i, s in enumerate(steps) if "attest-build-provenance" in s.get("uses", "")
    )
    publish = next(
        i for i, s in enumerate(steps) if "npm publish ./*.tgz" in s.get("run", "")
    )
    assert pack < verify < attest < publish
    assert steps[verify].get("continue-on-error", "false") == "false"
    assert any(s.get("run") == "npm ci" for s in steps)


def test_distribution_verification_is_in_required_pr_job():
    ci = workflow("ci.yml")
    assert "npm-package-tests" in ci["jobs"]["ci-required"]["needs"]
    steps = ci["jobs"]["npm-package-tests"]["steps"]
    step = next(s for s in steps if s.get("run") == "npm run test:distribution")
    assert step.get("continue-on-error", "false") == "false"
    commands = "\n".join(
        s.get("run", "") for s in ci["jobs"]["wasm-onnx-contract"]["steps"]
    )
    assert "test_npm_release_ci.py" in commands


def test_local_g2p_install_does_not_rewrite_packed_dependencies():
    steps = workflow("ci.yml")["jobs"]["npm-package-tests"]["steps"]
    installs = [s["run"] for s in steps if "file:../g2p" in s.get("run", "")]
    assert installs
    assert all("--no-save" in command for command in installs)


def _index(steps, needle, key="run"):
    return next(i for i, s in enumerate(steps) if needle in s.get(key, ""))


def test_cdn_delivery_checks_are_in_required_pr_job():
    # The browser tests serve local bytes for CDN URLs, so they could not see
    # jsDelivr refusing the ~60 MB G2P WASM (#818). These two steps can.
    ci = workflow("ci.yml")
    assert "npm-package-tests" in ci["jobs"]["ci-required"]["needs"]
    steps = ci["jobs"]["npm-package-tests"]["steps"]
    build = _index(steps, "wasm-pack build")
    check = _index(steps, "npm run check:cdn")
    browser = _index(steps, "npm run test:browser")
    real_cdn = _index(steps, "npm run test:real-cdn")
    assert build < check
    assert browser < real_cdn
    for i in (check, real_cdn):
        assert steps[i].get("continue-on-error", "false") == "false"
    package = json.loads(
        (ROOT / "src/wasm/openjtalk-web/package.json").read_text(encoding="utf-8")
    )
    assert "test-cdn-delivery.js" in package["scripts"]["test:npm-package:all"]


def test_publish_verifies_readme_on_real_cdns_after_publishing():
    steps = workflow("npm-publish.yml")["jobs"]["publish"]["steps"]
    publish = _index(steps, "npm publish ./*.tgz")
    real_cdn = _index(steps, "npm run test:real-cdn")
    assert publish < real_cdn
    # Without waiting for the registry the check skips itself after publishing.
    assert "--after-publish" in steps[real_cdn]["run"]
    assert steps[real_cdn].get("continue-on-error", "false") == "false"
