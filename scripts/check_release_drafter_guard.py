"""Protect prepared tag-backed or populated drafts from Release Drafter."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def protected_drafts(releases: list[dict], tags: set[str]) -> list[int]:
    return [
        release["id"]
        for release in releases
        if release["draft"] and (release["tag_name"] in tags or bool(release["assets"]))
    ]


def github_api(endpoint: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pages = json.loads(result.stdout)
    return [item for page in pages for item in page]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Invalid GitHub repository")
    releases = github_api(f"repos/{args.repository}/releases?per_page=100")
    refs = github_api(f"repos/{args.repository}/git/matching-refs/tags/")
    tags = {ref["ref"].removeprefix("refs/tags/") for ref in refs}
    protected = protected_drafts(releases, tags)
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"safe_to_update={'false' if protected else 'true'}\n")
    if protected:
        print(
            f"Prepared releases {protected}: preserve drafts and defer automatic notes"
        )
    else:
        print("No prepared release draft: automatic notes may be updated")


if __name__ == "__main__":
    main()
