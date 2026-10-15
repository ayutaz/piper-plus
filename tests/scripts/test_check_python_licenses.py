"""Negative cases for dependency closure and installed metadata auditing."""

import tomllib
from email.message import Message
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts.check_python_licenses import FORBIDDEN_DISTRIBUTIONS, audit


class Distribution:
    def __init__(self, name, requires=(), license="MIT", classifier=None):
        self.metadata = Message()
        self.metadata["Name"] = name
        self.metadata["Version"] = "1.0"
        self.metadata["License-Expression"] = license
        if classifier:
            self.metadata["Classifier"] = classifier
        self.version = "1.0"
        self.requires = list(requires)


def test_old_english_distributions_are_absent_from_every_python_lock():
    root = Path(__file__).resolve().parents[2]
    for relative in ("uv.lock", "environments/webui/uv.lock", "src/python/g2p/uv.lock"):
        lock = tomllib.loads((root / relative).read_text(encoding="utf-8"))
        names = {canonicalize_name(p["name"]) for p in lock["package"]}
        assert not names & FORBIDDEN_DISTRIBUTIONS, relative


def test_no_supported_extra_or_space_restores_old_english_dependency():
    root = Path(__file__).resolve().parents[2]
    declarations = []
    for relative in (
        "pyproject.toml",
        "src/python/pyproject.toml",
        "src/python_run/pyproject.toml",
        "src/python/g2p/pyproject.toml",
        "environments/webui/pyproject.toml",
    ):
        project = tomllib.loads((root / relative).read_text(encoding="utf-8"))[
            "project"
        ]
        declarations.extend(project.get("dependencies", []))
        for dependencies in project.get("optional-dependencies", {}).values():
            declarations.extend(dependencies)
    for relative in (
        "src/python_run/requirements.txt",
        "huggingface-space/requirements.txt",
    ):
        declarations.extend(
            line.split("#", 1)[0].strip()
            for line in (root / relative).read_text(encoding="utf-8").splitlines()
            if line.split("#", 1)[0].strip()
        )
    for declaration in declarations:
        assert (
            canonicalize_name(Requirement(declaration).name)
            not in FORBIDDEN_DISTRIBUTIONS
        )


def test_nested_gpl_dependency_is_rejected_even_with_an_unfamiliar_name():
    distributions = [
        Distribution("app", ["helper"]),
        Distribution("helper", ["copyleft-library"]),
        Distribution("copyleft-library", license="GPL-3.0-or-later"),
    ]
    result = audit(distributions, ["app"])
    assert any("copyleft-library" in e and "GPL" in e for e in result["errors"])


def test_gpl_classifier_is_not_hidden_by_unknown_license():
    dist = Distribution(
        "app",
        license="UNKNOWN",
        classifier="License :: OSI Approved :: GNU General Public License (GPL)",
    )
    assert audit([dist], ["app"])["errors"]


def test_missing_dependency_fails_closed():
    assert audit([Distribution("app", ["missing"])], ["app"])["errors"]


def test_optional_extra_is_included_only_when_selected():
    distributions = [
        Distribution("app", ['bad; extra == "en"']),
        Distribution("bad", license="LGPL-2.1-or-later"),
    ]
    assert not audit(distributions, ["app"])["errors"]
    assert audit(distributions, ["app[en]"])["errors"]


def test_transitive_extra_is_not_lost():
    distributions = [
        Distribution("app", ["helper[en]"]),
        Distribution("helper", ['bad; extra == "en"']),
        Distribution("bad", license="AGPL-3.0-only"),
    ]
    assert audit(distributions, ["app"])["errors"]


def test_version_mismatch_is_an_error():
    assert audit([Distribution("app", ["helper>=2"]), Distribution("helper")], ["app"])[
        "errors"
    ]


def test_unused_distance_installation_is_detected():
    result = audit([Distribution("app"), Distribution("Distance")], ["app"])
    assert any("distance" in e.lower() for e in result["errors"])


def test_permissive_licenses_are_retained_in_report():
    distributions = [
        Distribution("app", ["helper"]),
        Distribution("helper", license="Apache-2.0 AND CNRI-Python"),
    ]
    result = audit(distributions, ["app"])
    assert not result["errors"]
    assert set(result["packages"]) == {"app", "helper"}


def test_short_non_spdx_gpl_spelling_is_detected():
    assert audit([Distribution("app", license="GPLv3")], ["app"])["errors"]


def test_absent_license_fails_closed():
    assert audit([Distribution("app", license="")], ["app"])["errors"]
