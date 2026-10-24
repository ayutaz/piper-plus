#!/usr/bin/env python3
"""Keep the repository rulesets equal to .github/rulesets/*.json.

The rulesets decide what can be merged into ``dev`` and which tags can be
moved or deleted, but they lived only in the repository settings, so a change
made there left no record and no review. Each file in ``.github/rulesets/`` is
the payload of one ruleset (``name``, ``target``, ``enforcement``,
``conditions``, ``rules``, ``bypass_actors``), matched to the live ruleset by
``name``.

Modes:

``--validate`` (no network)
    Checks the files themselves: the merge requirements on ``dev`` (the
    required checks, unresolved threads blocking merge, ``strict`` off, no
    bypass) and that the tag ruleset blocks deleting and moving every release
    tag, ``v*``, ``*-v*`` and ``src/go/**``, and not the two moving tags
    (``openjtalk-binaries-latest``, ``dev-20250610``). With ``--tags FILE``
    (one tag name per line) every listed tag must be covered or be one of
    those two.

``--check`` (default; reads the API through ``gh``)
    Prints the difference between each file and the live ruleset and fails
    on any difference. It also lists the live tags and fails on a tag the
    tag ruleset does not cover. ``bypass_actors`` is returned only to admins;
    when the token cannot see it, that field is skipped with a notice.

``--apply`` (admin only)
    Prints the same difference, then updates the live rulesets (creating a
    ruleset whose name does not exist yet) and reads them back.

Exit codes: 0 = no difference / applied, 1 = difference or invalid file,
2 = the API could not be read.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULESETS_DIR = REPO_ROOT / ".github" / "rulesets"
DEFAULT_REPO = "ayutaz/piper-plus"

FIELDS = ("name", "target", "enforcement", "conditions", "rules", "bypass_actors")

# What dev must require before a merge (CONTRIBUTING.md, "マージ条件とタグの保護").
DEV_RULESET = "piper-dev"
DEV_REQUIRED_CHECKS = {"ci-required", "required-gate/all-workflows"}
TAG_RULESET = "release-tags"
TAG_REQUIRED_RULES = {"deletion", "non_fast_forward", "update"}
# Tags that are moved on purpose and must stay outside the tag ruleset.
MOVING_TAGS = {"openjtalk-binaries-latest", "dev-20250610"}
RELEASE_TAG_SAMPLES = [
    "v2.0.2",
    "npm-v0.8.2",
    "docker-signatures-v2.0.0",
    "python-g2p-v0.3.1",
    "src/go/v0.2.0",
    "src/go/phonemize/v0.3.0",
]


class ApiError(RuntimeError):
    pass


def ref_pattern_regex(pattern: str) -> re.Pattern[str]:
    """Ruleset ``ref_name`` matching: ``*`` stops at ``/``, ``**`` does not."""
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def ref_covered(ruleset: dict, ref: str) -> bool:
    names = ruleset.get("conditions", {}).get("ref_name", {})
    if any(ref_pattern_regex(p).match(ref) for p in names.get("exclude", [])):
        return False
    return any(ref_pattern_regex(p).match(ref) for p in names.get("include", []))


def load_desired(directory: Path = RULESETS_DIR) -> dict[str, dict]:
    desired: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = [f for f in FIELDS if f not in data]
        extra = sorted(set(data) - set(FIELDS))
        if missing or extra:
            raise ValueError(f"{path.name}: missing {missing}, unexpected {extra}")
        if path.stem != data["name"]:
            raise ValueError(f"{path.name}: file name must be the ruleset name {data['name']!r}")
        desired[data["name"]] = data
    return desired


def _rule(ruleset: dict, rule_type: str) -> dict | None:
    return next((r for r in ruleset.get("rules", []) if r.get("type") == rule_type), None)


def validate(desired: dict[str, dict], tags: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    dev = desired.get(DEV_RULESET)
    if dev is None:
        errors.append(f"no {DEV_RULESET}.json")
    else:
        if not ref_covered(dev, "refs/heads/dev"):
            errors.append(f"{DEV_RULESET}: does not cover refs/heads/dev")
        if dev["enforcement"] != "active":
            errors.append(f"{DEV_RULESET}: enforcement must be active")
        if dev["bypass_actors"]:
            errors.append(f"{DEV_RULESET}: bypass_actors must be empty")
        checks = _rule(dev, "required_status_checks")
        params = (checks or {}).get("parameters", {})
        contexts = {c["context"] for c in params.get("required_status_checks", [])}
        if not DEV_REQUIRED_CHECKS <= contexts:
            errors.append(
                f"{DEV_RULESET}: required checks {sorted(contexts)} lack "
                f"{sorted(DEV_REQUIRED_CHECKS - contexts)}"
            )
        if params.get("strict_required_status_checks_policy") is not False:
            errors.append(f"{DEV_RULESET}: strict_required_status_checks_policy must be false")
        pr = (_rule(dev, "pull_request") or {}).get("parameters", {})
        if pr.get("required_review_thread_resolution") is not True:
            errors.append(f"{DEV_RULESET}: required_review_thread_resolution must be true")
        for rule_type in ("deletion", "non_fast_forward"):
            if _rule(dev, rule_type) is None:
                errors.append(f"{DEV_RULESET}: missing rule {rule_type}")

    tag = desired.get(TAG_RULESET)
    if tag is None:
        errors.append(f"no {TAG_RULESET}.json")
        return errors
    if tag["target"] != "tag":
        errors.append(f"{TAG_RULESET}: target must be tag")
    if tag["enforcement"] != "active":
        errors.append(f"{TAG_RULESET}: enforcement must be active")
    if tag["bypass_actors"]:
        errors.append(f"{TAG_RULESET}: bypass_actors must be empty (no exceptions)")
    types = {r["type"] for r in tag["rules"]}
    if not TAG_REQUIRED_RULES <= types:
        errors.append(f"{TAG_RULESET}: missing rules {sorted(TAG_REQUIRED_RULES - types)}")
    for name in RELEASE_TAG_SAMPLES:
        if not ref_covered(tag, f"refs/tags/{name}"):
            errors.append(f"{TAG_RULESET}: release tag {name} is not covered")
    for name in sorted(MOVING_TAGS):
        if ref_covered(tag, f"refs/tags/{name}"):
            errors.append(f"{TAG_RULESET}: {name} is moved on purpose and must not be covered")
    for name in tags or []:
        if name not in MOVING_TAGS and not ref_covered(tag, f"refs/tags/{name}"):
            errors.append(f"{TAG_RULESET}: tag {name} is not covered")
    return errors


def normalize(ruleset: dict, *, include_bypass: bool = True) -> dict:
    """The compared fields, with order-free lists sorted."""
    out = {f: ruleset.get(f) for f in FIELDS if include_bypass or f != "bypass_actors"}
    names = dict(out.get("conditions", {}).get("ref_name", {}))
    for key in ("include", "exclude"):
        names[key] = sorted(names.get(key, []))
    out["conditions"] = {**(out.get("conditions") or {}), "ref_name": names}
    rules = []
    for rule in ruleset.get("rules", []):
        rule = json.loads(json.dumps(rule))
        params = rule.get("parameters")
        if params and "required_status_checks" in params:
            params["required_status_checks"] = sorted(
                params["required_status_checks"], key=lambda c: c["context"]
            )
        if params and "allowed_merge_methods" in params:
            params["allowed_merge_methods"] = sorted(params["allowed_merge_methods"])
        rules.append(rule)
    out["rules"] = sorted(rules, key=lambda r: r["type"])
    return out


def render_diff(name: str, desired: dict, live: dict | None, *, include_bypass: bool = True) -> str:
    want = json.dumps(normalize(desired, include_bypass=include_bypass), indent=2, sort_keys=True)
    have = (
        json.dumps(normalize(live, include_bypass=include_bypass), indent=2, sort_keys=True)
        if live is not None
        else ""
    )
    return "".join(
        difflib.unified_diff(
            have.splitlines(keepends=True),
            want.splitlines(keepends=True),
            fromfile=f"live/{name}" if live is not None else "live/(none)",
            tofile=f".github/rulesets/{name}.json",
        )
    )


def gh_api(path: str, *, method: str = "GET", body: dict | None = None, paginate: bool = False):
    cmd = ["gh", "api", path, "--method", method]
    if paginate:
        cmd.append("--paginate")
    if body is not None:
        cmd += ["--input", "-"]
    proc = subprocess.run(
        cmd,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise ApiError(f"gh api {method} {path} failed: {proc.stderr.strip()}")
    text = proc.stdout.strip()
    if paginate:
        # --paginate concatenates one JSON array per page.
        return [item for page in re.split(r"(?<=\])\s*(?=\[)", text) if page for item in json.loads(page)]
    return json.loads(text) if text else None


def live_rulesets(repo: str) -> dict[str, dict]:
    listed = gh_api(f"repos/{repo}/rulesets?includes_parents=false&per_page=100", paginate=True)
    return {r["name"]: gh_api(f"repos/{repo}/rulesets/{r['id']}") for r in listed}


def live_tags(repo: str) -> list[str]:
    return [t["name"] for t in gh_api(f"repos/{repo}/tags?per_page=100", paginate=True)]


def compare(desired: dict[str, dict], live: dict[str, dict]) -> tuple[list[str], list[str]]:
    diffs: list[str] = []
    notices: list[str] = []
    for name, want in desired.items():
        have = live.get(name)
        include_bypass = have is None or "bypass_actors" in have
        if not include_bypass:
            notices.append(f"{name}: bypass_actors is not visible to this token; not compared")
        diff = render_diff(name, want, have, include_bypass=include_bypass)
        if diff:
            diffs.append(diff)
    return diffs, notices


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--dir", type=Path, default=RULESETS_DIR)
    parser.add_argument("--tags", type=Path, help="--validate: file with one tag name per line")
    args = parser.parse_args(argv)

    try:
        desired = load_desired(args.dir)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.validate:
        tags = (
            [t.strip() for t in args.tags.read_text(encoding="utf-8").splitlines() if t.strip()]
            if args.tags
            else None
        )
        errors = validate(desired, tags)
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        if not errors:
            print(f"OK: {len(desired)} ruleset files are valid")
        return 1 if errors else 0

    errors = validate(desired)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    try:
        live = live_rulesets(args.repo)
        diffs, notices = compare(desired, live)
        for notice in notices:
            print(f"NOTICE: {notice}")
        if not args.apply:
            uncovered = [
                t
                for t in live_tags(args.repo)
                if t not in MOVING_TAGS and not ref_covered(desired[TAG_RULESET], f"refs/tags/{t}")
            ]
            for diff in diffs:
                print(diff)
            for t in uncovered:
                print(f"ERROR: live tag {t} is not covered by {TAG_RULESET}", file=sys.stderr)
            if diffs or uncovered:
                print(
                    "Live rulesets differ from .github/rulesets/. Change the file in a "
                    "pull request, then run `scripts/check_rulesets.py --apply` as an admin.",
                    file=sys.stderr,
                )
                return 1
            print(f"OK: {len(desired)} live rulesets match .github/rulesets/")
            return 0

        for diff in diffs:
            print(diff)
        for name, want in desired.items():
            body = {f: want[f] for f in FIELDS}
            if name in live:
                gh_api(f"repos/{args.repo}/rulesets/{live[name]['id']}", method="PUT", body=body)
                print(f"updated {name}")
            else:
                gh_api(f"repos/{args.repo}/rulesets", method="POST", body=body)
                print(f"created {name}")
        diffs, _ = compare(desired, live_rulesets(args.repo))
        if diffs:
            print("ERROR: read-back still differs:", file=sys.stderr)
            for diff in diffs:
                print(diff, file=sys.stderr)
            return 1
        print("OK: read-back matches .github/rulesets/")
        return 0
    except ApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
