"""A release wheel must include the modules and dictionaries its users need."""

import ast
import importlib.util
import tomllib
import zipfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "verify_python_wheel", ROOT / "scripts/check_python_release_wheel.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def wheel(
    tmp_path,
    *,
    version="2.0.0",
    missing=None,
    legacy=False,
    dependency=None,
    corrupt=None,
    g2p=False,
):
    target = tmp_path / "package.whl"
    files = {
        "piper_plus/__init__.py": "",
        "piper_plus/voice.py": "",
        "piper_plus/__main__.py": "",
        "piper_plus/phonemize/data/zh_en_loanword.json": "{}",
        "piper_plus/phonemize/data/sv_function_words.json": "{}",
        "piper_plus-2.0.0.dist-info/METADATA": f"Name: piper-plus\nVersion: {version}\n",
        "piper_plus-2.0.0.dist-info/licenses/LICENSE.md": "MIT license fixture",
    }
    vendor = ROOT / "src/python_run/piper_plus/_vendor/g2p_en"
    files.update(
        {
            f"piper_plus/_vendor/g2p_en/{p.name}": p.read_bytes()
            for p in vendor.iterdir()
            if p.is_file()
        }
    )
    if dependency:
        files["piper_plus-2.0.0.dist-info/METADATA"] += f"Requires-Dist: {dependency}\n"
    if g2p:
        files = {
            name.replace("piper_plus/", "piper_plus_g2p/"): value
            for name, value in files.items()
        }
        files["piper_plus-2.0.0.dist-info/METADATA"] = files[
            "piper_plus-2.0.0.dist-info/METADATA"
        ].replace("Name: piper-plus\n", "Name: piper-plus-g2p\n")
        files.update(
            {
                f"piper_plus_g2p/{name}": "{}"
                for name in (
                    "registry.py",
                    "ssml.py",
                    "data/pua.json",
                    "data/zh_en_loanword.json",
                    "data/sv_function_words.json",
                    "THIRD_PARTY_LICENSES.md",
                )
            }
        )
    if corrupt:
        files[corrupt] = b"corrupt"
    if missing:
        files.pop(missing)
    if legacy:
        files["piper/__init__.py"] = ""
    with zipfile.ZipFile(target, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return target


def test_accepts_complete_wheel(tmp_path):
    MODULE.verify_wheel(wheel(tmp_path), "piper-plus", "2.0.0")


def test_accepts_complete_g2p_wheel(tmp_path):
    MODULE.verify_wheel(wheel(tmp_path, g2p=True), "piper-plus-g2p", "2.0.0")


def test_wrong_version_fails(tmp_path):
    with pytest.raises(ValueError, match="version"):
        MODULE.verify_wheel(wheel(tmp_path, version="0.0.0"), "piper-plus", "2.0.0")


@pytest.mark.parametrize(
    "missing",
    [
        "piper_plus/voice.py",
        "piper_plus/phonemize/data/zh_en_loanword.json",
        "piper_plus/phonemize/data/sv_function_words.json",
        "piper_plus-2.0.0.dist-info/licenses/LICENSE.md",
    ],
)
def test_missing_runtime_files_fail(tmp_path, missing):
    with pytest.raises(ValueError, match="missing"):
        MODULE.verify_wheel(wheel(tmp_path, missing=missing), "piper-plus", "2.0.0")


def test_legacy_piper_module_is_not_shipped(tmp_path):
    with pytest.raises(ValueError, match="legacy"):
        MODULE.verify_wheel(wheel(tmp_path, legacy=True), "piper-plus", "2.0.0")


@pytest.mark.parametrize(
    "dependency", ["Distance>=0.1.3", "g2p_en==2.1.0; extra == 'en'", "G2P.EN"]
)
def test_old_english_dependencies_fail_even_in_extras(tmp_path, dependency):
    with pytest.raises(ValueError, match="dependency"):
        MODULE.verify_wheel(
            wheel(tmp_path, dependency=dependency), "piper-plus", "2.0.0"
        )


@pytest.mark.parametrize(
    "asset",
    [
        "checkpoint20.npz",
        "LICENSE.txt",
        "TACOTRON-LICENSE.txt",
        "NOTICE.txt",
        "provenance.json",
    ],
)
@pytest.mark.parametrize("operation", ["missing", "corrupt"])
@pytest.mark.parametrize("g2p", [False, True])
def test_missing_or_changed_english_payload_fails(tmp_path, asset, operation, g2p):
    package = "piper_plus_g2p" if g2p else "piper_plus"
    with pytest.raises(ValueError, match=r"[Bb]undled English"):
        MODULE.verify_wheel(
            wheel(
                tmp_path, g2p=g2p, **{operation: f"{package}/_vendor/g2p_en/{asset}"}
            ),
            package.replace("_", "-"),
            "2.0.0",
        )


@pytest.mark.parametrize(
    "filename,job",
    [("dev-create-release.yml", "publish_pypi"), ("g2p-python-ci.yml", "publish")],
)
def test_publication_requires_installed_wheel_license_and_audio_checks(filename, job):
    config = yaml.load(
        (ROOT / ".github/workflows" / filename).read_text("utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert (
        config["jobs"]["release-license"]["uses"]
        == "./.github/workflows/python-license.yml"
    )
    assert "release-license" in config["jobs"][job]["needs"]
    if job == "publish_pypi":
        assert "needs.release-license.result == 'success'" in config["jobs"][job]["if"]
    scripts = "\n".join(step.get("run", "") for step in config["jobs"][job]["steps"])
    assert "check_bundled_english.py" in scripts
    assert "check_python_release_wheel.py" in scripts


def test_g2p_module_version_matches_distribution_metadata():
    package = ROOT / "src/python/g2p"
    manifest = tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))
    module = ast.parse(
        (package / "piper_plus_g2p/__init__.py").read_text(encoding="utf-8")
    )
    version = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
    )
    assert version == manifest["project"]["version"]
