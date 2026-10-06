"""The exact packed distribution must pass before npm publication and on PRs."""

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
        i for i, s in enumerate(steps)
        if "npm run test:distribution -- *.tgz" in s.get("run", "")
    )
    attest = next(i for i, s in enumerate(steps) if "attest-build-provenance" in s.get("uses", ""))
    publish = next(i for i, s in enumerate(steps) if "npm publish *.tgz" in s.get("run", ""))
    assert pack < verify < attest < publish
    assert steps[verify].get("continue-on-error", "false") == "false"
    assert any(s.get("run") == "npm ci" for s in steps)


def test_distribution_verification_is_in_required_pr_job():
    ci = workflow("ci.yml")
    assert "npm-package-tests" in ci["jobs"]["ci-required"]["needs"]
    steps = ci["jobs"]["npm-package-tests"]["steps"]
    step = next(s for s in steps if s.get("run") == "npm run test:distribution")
    assert step.get("continue-on-error", "false") == "false"
    commands = "\n".join(s.get("run", "") for s in ci["jobs"]["wasm-onnx-contract"]["steps"])
    assert "test_npm_release_ci.py" in commands
