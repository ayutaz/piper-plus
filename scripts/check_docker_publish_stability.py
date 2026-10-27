"""Check publication invariants without building or accessing registries."""

import re
from pathlib import Path

import yaml


# A pull request reads the cache and writes none: its cache was evicted
# before its next push read it. The export is written only on a push.
PUSH_ONLY_RE = re.compile(
    r"\$\{\{\s*github\.event_name != 'pull_request' && "
    r"(?:'(?P<plain>[^']*)'|format\('(?P<fmt>[^']*)',\s*(?P<arg>[\w.]+)\))"
    r" \|\| '' \}\}"
)


def cache_export(value):
    """The cache-to spec a push uses, or None if a pull request exports too."""
    m = PUSH_ONLY_RE.fullmatch(value.strip())
    if not m:
        return None
    if m.group("plain") is not None:
        return m.group("plain")
    return m.group("fmt").replace("{0}", "${{ " + m.group("arg") + " }}")


def pr_load(step):
    """A pull-request-only build that loads an image for tests and publishes nothing.

    A multi-platform build cannot be loaded into docker, so a job that
    publishes one may load a single platform from the same builder on a
    pull request. It pushes nothing, so it cannot change a published digest.
    """
    options = step.get("with", {})
    return (
        step.get("if", "").strip() == "github.event_name == 'pull_request'"
        and options.get("push") is False
        and options.get("load") is True
    )


def check(data):
    errors = []
    scopes = set()
    for name, job in data["jobs"].items():
        steps = [
            s
            for s in job["steps"]
            if s.get("uses", "").startswith("docker/build-push-action@")
        ]
        builds = [s for s in steps if not pr_load(s)]
        for step in steps:
            if pr_load(step) and "cache-to" in step.get("with", {}):
                errors.append(f"{name}: a pull request must not export the cache")
        if not builds:
            continue
        if len(builds) != 1:
            errors.append(f"{name}: build once, mirror the same digest")
        if not 0 < job.get("timeout-minutes", 0) <= 240:
            errors.append(f"{name}: missing bounded job timeout")
        for step in builds:
            options = step.get("with", {})
            spec = cache_export(options.get("cache-to", ""))
            if spec is None:
                errors.append(f"{name}: a pull request must not export the cache")
                spec = options.get("cache-to", "")
            cache = dict(p.split("=", 1) for p in spec.split(",") if "=" in p)
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
