"""Unit tests for scripts/check_action_sha_drift.py (T-002)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_action_sha_drift.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "action-sha-drift"


def _load_module():
    # Ensure platform_utils is importable from scripts/
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_action_sha_drift",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drift():
    return _load_module()


@pytest.fixture
def workflow_dir(tmp_path: Path) -> Path:
    d = tmp_path / "workflows"
    d.mkdir()
    return d


def _write_workflow(d: Path, name: str, body: str) -> Path:
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def test_collect_sha_pins_only_extracts_40hex(drift, workflow_dir: Path):
    _write_workflow(
        workflow_dir,
        "wf.yml",
        """
jobs:
  build:
    steps:
      - uses: actions/checkout@v6.0.2
      - uses: dawidd6/action-download-artifact@8a338493df3d275e4a7a63bcff3b8fe97e51a927  # v19
      - uses: ./.github/actions/local-thing
      - uses: foo/bar@v4
""",
    )
    pins = drift.collect_sha_pins(workflow_dir)
    assert pins == [
        (
            "dawidd6/action-download-artifact",
            "8a338493df3d275e4a7a63bcff3b8fe97e51a927",
        ),
    ]


def test_collect_sha_pins_handles_subpath_uses(drift, workflow_dir: Path):
    _write_workflow(
        workflow_dir,
        "wf.yml",
        """
jobs:
  build:
    steps:
      - uses: foo/bar/subpath@1111111111111111111111111111111111111111
""",
    )
    pins = drift.collect_sha_pins(workflow_dir)
    assert pins == [("foo/bar/subpath", "1111111111111111111111111111111111111111")]


def test_run_drift_check_ok_status(drift):
    pins = [("foo/bar", "a" * 40)]
    baseline = {"ignore_actions": []}

    def resolver(action: str, sha: str):
        return {"status": "ok", "resolved_tag": "v1.2.3"}

    results = drift.run_drift_check(pins, baseline, resolver)
    assert results == [
        {
            "action": "foo/bar",
            "sha": "a" * 40,
            "status": "ok",
            "resolved_tag": "v1.2.3",
        }
    ]


def test_run_drift_check_dangling_status(drift):
    pins = [("foo/bar", "b" * 40)]

    def resolver(action: str, sha: str):
        return {"status": "dangling", "error": "tag not reachable"}

    results = drift.run_drift_check(pins, {}, resolver)
    assert results[0]["status"] == "dangling"


def test_run_drift_check_force_pushed_status(drift):
    pins = [("foo/bar", "c" * 40)]

    def resolver(action: str, sha: str):
        return {"status": "force-pushed", "error": "404 not found"}

    results = drift.run_drift_check(pins, {}, resolver)
    assert results[0]["status"] == "force-pushed"


def test_run_drift_check_respects_ignore_actions(drift):
    pins = [("ignored/thing", "d" * 40), ("foo/bar", "e" * 40)]
    baseline = {"ignore_actions": ["ignored/thing"]}

    def resolver(action: str, sha: str):
        # Should never be called for ignored/thing.
        assert action != "ignored/thing"
        return {"status": "ok", "resolved_tag": "v1"}

    results = drift.run_drift_check(pins, baseline, resolver)
    statuses = [r["status"] for r in results]
    assert statuses == ["ignored", "ok"]


def test_main_silent_zero_warning_when_pin_count_dropped(
    drift,
    workflow_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    # 1 pin scanned but expected_total_pins=10 → ratio 0.1 < 0.5 → warning.
    _write_workflow(
        workflow_dir,
        "wf.yml",
        """
jobs:
  build:
    steps:
      - uses: foo/bar@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
""",
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "expected_total_pins": 10,
                "allowlist": [
                    {
                        "action": "foo/bar",
                        "sha": "a" * 40,
                        "resolved_tag": "v1",
                        "verified_at": "2026-01-01T00:00:00Z",
                    }
                ],
                "ignore_actions": [],
            }
        )
    )
    rc = drift.main(
        [
            "--workflows-dir",
            str(workflow_dir),
            "--baseline",
            str(baseline_path),
            "--offline",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "::warning::Collected pins (1)" in captured.err
    assert "Collected pins (1 actions): foo/bar@aaaaaaa" in captured.err


def test_main_defensive_log_always_emitted_even_when_zero_pins(
    drift,
    workflow_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    # No workflows → 0 pins → defensive log MUST still appear.
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "expected_total_pins": 0,
                "allowlist": [],
                "ignore_actions": [],
            }
        )
    )
    rc = drift.main(
        [
            "--workflows-dir",
            str(workflow_dir),
            "--baseline",
            str(baseline_path),
            "--offline",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "Collected pins (0 actions): (none)" in captured.err


def test_main_offline_dangling_when_sha_not_in_baseline(
    drift,
    workflow_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    _write_workflow(
        workflow_dir,
        "wf.yml",
        """
jobs:
  build:
    steps:
      - uses: foo/bar@1234567890abcdef1234567890abcdef12345678
""",
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "expected_total_pins": 1,
                "allowlist": [],  # empty — pin is not allowlisted → dangling.
                "ignore_actions": [],
            }
        )
    )
    rc = drift.main(
        [
            "--workflows-dir",
            str(workflow_dir),
            "--baseline",
            str(baseline_path),
            "--offline",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "**DANGLING**" in captured.out
    assert "Summary: total=1, dangling=1" in captured.out


def test_main_rejects_unknown_schema_version(
    drift,
    workflow_dir: Path,
    tmp_path: Path,
):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "expected_total_pins": 0,
                "allowlist": [],
                "ignore_actions": [],
            }
        )
    )
    with pytest.raises(ValueError, match="schema_version"):
        drift.main(
            [
                "--workflows-dir",
                str(workflow_dir),
                "--baseline",
                str(baseline_path),
                "--offline",
            ]
        )


def test_resolve_sha_via_api_returns_force_pushed_on_404(
    drift,
    monkeypatch: pytest.MonkeyPatch,
):
    import urllib.error

    def fake_urlopen(req, timeout=10.0):
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b""),
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen,
    )
    result = drift.resolve_sha_via_api("foo/bar", "a" * 40)
    assert result["status"] == "force-pushed"
    assert "404" in result["error"]


def test_resolve_sha_via_api_returns_ok_on_200(
    drift,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(
                {
                    "sha": "a" * 40,
                    "html_url": "https://github.com/foo/bar/commit/aaaa",
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=10.0: FakeResponse(),
    )
    result = drift.resolve_sha_via_api("foo/bar", "a" * 40)
    assert result["status"] == "ok"
    assert result["resolved_tag"] == "(commit-only)"


def test_fixture_baseline_ok_round_trip(drift, tmp_path: Path):
    """baseline_ok fixture should produce all-ok against itself."""
    fixture = FIXTURES / "baseline_ok.json"
    assert fixture.exists(), f"Missing fixture: {fixture}"
    baseline = json.loads(fixture.read_text(encoding="utf-8"))
    assert baseline["schema_version"] == 1
    pins = [(a["action"], a["sha"]) for a in baseline["allowlist"]]
    resolver = drift._offline_resolver(baseline)
    results = drift.run_drift_check(pins, baseline, resolver)
    assert all(r["status"] == "ok" for r in results)


def test_fixture_baseline_half_missing_triggers_silent_zero(
    drift,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    workflow_dir: Path,
):
    """baseline_half_missing fixture has expected_total_pins=10 but scanning
    finds 2 — silent-zero ratio (0.2) is below 0.5, so we expect a warning."""
    _write_workflow(
        workflow_dir,
        "wf.yml",
        """
jobs:
  build:
    steps:
      - uses: foo/bar@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      - uses: foo/baz@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
""",
    )
    fixture = FIXTURES / "baseline_half_missing.json"
    assert fixture.exists(), f"Missing fixture: {fixture}"
    rc = drift.main(
        [
            "--workflows-dir",
            str(workflow_dir),
            "--baseline",
            str(fixture),
            "--offline",
        ]
    )
    captured = capsys.readouterr()
    # rc may be 0 or 1 depending on whether the 2 scanned pins are in the
    # fixture allowlist; the assert we care about is the silent-zero warning.
    assert rc in (0, 1)
    assert "::warning::Collected pins (2)" in captured.err
    assert "expected_total_pins (10)" in captured.err
