"""Release Docker tags must resolve to the approved numeric version."""

import ast
import re
from pathlib import Path

import pytest
import yaml


def test_docker_prefixed_tags_are_numeric_in_all_registry_metadata():
    root = Path(__file__).resolve().parents[2]
    data = yaml.safe_load(
        (root / ".github/workflows/docker-build.yml").read_text(encoding="utf-8")
    )
    metadata = [
        step
        for job in data["jobs"].values()
        for step in job["steps"]
        if step.get("uses", "").startswith("docker/metadata-action@")
    ]
    assert len(metadata) >= 6
    for step in metadata:
        assert "type=match,pattern=docker-v(.*),group=1" in step["with"]["tags"], step[
            "id"
        ]


def test_inference_images_require_the_regression_gate():
    root = Path(__file__).resolve().parents[2]
    data = yaml.safe_load(
        (root / ".github/workflows/docker-build.yml").read_text(encoding="utf-8")
    )
    for name in ["build-python-inference", "build-python-inference-cpu", "build-webui"]:
        assert data["jobs"][name]["needs"] == "inference-regression"
    steps = data["jobs"]["inference-regression"]["steps"]
    assert any("test_phoneme_encoding.py" in step.get("run", "") for step in steps)


@pytest.mark.parametrize(
    "job",
    [
        "build-python-inference",
        "build-python-inference-cpu",
        "build-python-train",
        "build-cpp-dev",
        "build-cpp-inference",
        "build-wyoming",
        "build-webui",
    ],
)
@pytest.mark.parametrize("step_name", ["Install Cosign", "Sign the published image"])
@pytest.mark.parametrize(
    "reference,expected",
    [
        ("refs/tags/docker-v2.0.0", True),
        ("refs/tags/v2.0.0", True),
        ("refs/heads/dev", False),
        ("refs/pull/778/merge", False),
    ],
)
def test_release_tags_sign_every_image(job, step_name, reference, expected):
    root = Path(__file__).resolve().parents[2]
    data = yaml.safe_load(
        (root / ".github/workflows/docker-build.yml").read_text(encoding="utf-8")
    )
    step = next(s for s in data["jobs"][job]["steps"] if s.get("name") == step_name)
    expression = re.sub(
        r"startsWith\(github\.ref,\s*'([^']+)'\)",
        lambda match: str(reference.startswith(match[1])),
        step["if"],
    ).replace("||", "or").replace("&&", "and")
    tree = ast.parse(expression, mode="eval")
    assert all(
        isinstance(node, (ast.Expression, ast.BoolOp, ast.Or, ast.And, ast.Constant))
        for node in ast.walk(tree)
    )

    def value(node):
        if isinstance(node, ast.Constant):
            assert isinstance(node.value, bool)
            return node.value
        values = [value(child) for child in node.values]
        return any(values) if isinstance(node.op, ast.Or) else all(values)

    assert value(tree.body) is expected
