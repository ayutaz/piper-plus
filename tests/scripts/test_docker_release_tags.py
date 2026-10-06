"""Release Docker tags must resolve to the approved numeric version."""

from pathlib import Path

import yaml


def test_docker_prefixed_tags_are_numeric_in_all_registry_metadata():
    root = Path(__file__).resolve().parents[2]
    data = yaml.safe_load((root / ".github/workflows/docker-build.yml").read_text(encoding="utf-8"))
    metadata = [
        step
        for job in data["jobs"].values()
        for step in job["steps"]
        if step.get("uses", "").startswith("docker/metadata-action@")
    ]
    assert len(metadata) >= 6
    for step in metadata:
        assert "type=match,pattern=docker-v(.*),group=1" in step["with"]["tags"], step["id"]
