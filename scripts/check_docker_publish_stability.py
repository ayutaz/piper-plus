"""Check publication invariants without building or accessing registries."""

from pathlib import Path

import yaml


def check(data):
    errors = []
    scopes = set()
    for name, job in data["jobs"].items():
        builds = [
            s
            for s in job["steps"]
            if s.get("uses", "").startswith("docker/build-push-action@")
        ]
        if not builds:
            continue
        if len(builds) != 1:
            errors.append(f"{name}: build once, mirror the same digest")
        if not 0 < job.get("timeout-minutes", 0) <= 240:
            errors.append(f"{name}: missing bounded job timeout")
        for step in builds:
            options = step.get("with", {})
            cache = dict(
                p.split("=", 1)
                for p in options.get("cache-to", "").split(",")
                if "=" in p
            )
            scope = cache.get("scope")
            if not scope or scope in scopes:
                errors.append(f"{name}: cache scope missing or shared")
            scopes.add(scope)
            if cache.get("timeout") != "2m" or cache.get("ignore-error") != "true":
                errors.append(f"{name}: cache export must be bounded and optional")
            if scope and f"scope={scope}" not in options.get("cache-from", ""):
                errors.append(f"{name}: import/export cache scope differs")
        hub = [s for s in job["steps"] if s.get("name") == "Push to Docker Hub"]
        if hub and "publish_docker_mirror.py" not in hub[0].get("run", ""):
            errors.append(f"{name}: Docker Hub must preserve the GHCR digest")
    return errors


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    problems = check(
        yaml.safe_load(
            (root / ".github/workflows/docker-build.yml").read_text(encoding="utf-8")
        )
    )
    for problem in problems:
        print(problem)
    raise SystemExit(bool(problems))
