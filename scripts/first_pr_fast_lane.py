#!/usr/bin/env python3
"""First-PR fast lane (M1.3 — contract gate downgrade for new contributors).

`piper-plus` は 18+ contract gate を持つため、 初回 contributor は事実上
PR を merge できない状態になっている (親調査 §4 「CI as a moat 誤謬」)。
本 script は author_association が ``FIRST_TIME_CONTRIBUTOR`` /
``FIRST_TIMER`` / ``NONE`` のいずれかで、 ``run-full-gate`` label が
付いていない PR に対して、 監視対象 contract gate の check-run conclusion
を ``neutral`` に書き換える。 GitHub branch protection は ``neutral`` を
pass 扱いするため、 contract gate は warning として残るが merge は可能と
なる。

サブコマンド:

* ``evaluate``: 標準出力に ``fast_lane=true|false`` を ``$GITHUB_OUTPUT``
  形式で書く。 stderr に判定理由を出す。
* ``neutralize``: 指定 head_sha の check-run を取得し、 contract gate に
  該当する run の ``conclusion=failure`` を ``neutral`` に PATCH する。
  既に ``neutral`` / ``success`` / ``in_progress`` のものは触らない。
* ``comment``: PR に sticky comment を upsert する (`<!-- first-pr-fast-lane -->`
  marker 駆動)。

stdlib only (`urllib` + `json`)、 retry は exponential backoff。
``--runs-json`` / ``--head-sha-of-runs-json`` を渡すと REST を mock。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


GITHUB_API = "https://api.github.com"
USER_AGENT = "piper-plus-first-pr-fast-lane/1.0"
STICKY_MARKER = "<!-- first-pr-fast-lane -->"

# author_association values that count as "first-PR" for fast lane purposes.
# Reference: https://docs.github.com/en/rest/issues/comments#about-the-author-association
FAST_LANE_ASSOCIATIONS = frozenset({"FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE"})

# Label that maintainers can attach to promote the contract gate set back to
# blocker. Keep the name short so it is easy to type / remove via GitHub UI.
PROMOTE_LABEL = "run-full-gate"


@dataclass(frozen=True)
class CheckRun:
    id: int
    name: str
    status: str
    conclusion: str | None


def gh_request(
    method: str,
    path: str,
    token: str,
    *,
    body: dict | None = None,
    max_retries: int = 4,
) -> dict:
    url = f"{GITHUB_API}{path}"
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    backoff = 1.0
    last_err: Exception | None = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            data=payload,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (403, 429, 502, 503) and attempt < max_retries - 1:
                time.sleep(min(backoff, 60))
                backoff *= 2
                continue
            raise
        except urllib.error.URLError as exc:
            last_err = exc
            if attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise
    raise RuntimeError(f"gh_request failed: {last_err}")


def evaluate(author_association: str, labels: list[str]) -> tuple[bool, str]:
    """Return ``(is_fast_lane, reason)``.

    The promotion label always wins: once a maintainer attaches it, the PR
    must go through the full gate matrix even if the author still looks
    first-time to GitHub.
    """
    if PROMOTE_LABEL in labels:
        return False, f"{PROMOTE_LABEL!r} label promotes back to full-gate"
    if author_association in FAST_LANE_ASSOCIATIONS:
        return True, f"author_association={author_association} qualifies for fast lane"
    return False, f"author_association={author_association} is past first-PR"


def parse_labels(arg: str) -> list[str]:
    return [s.strip() for s in arg.split(",") if s.strip()]


def fetch_check_runs(repo: str, head_sha: str, token: str) -> list[CheckRun]:
    data = gh_request(
        "GET",
        f"/repos/{repo}/commits/{head_sha}/check-runs?per_page=100",
        token,
    )
    return [
        CheckRun(
            id=int(r["id"]),
            name=r["name"],
            status=r.get("status", ""),
            conclusion=r.get("conclusion"),
        )
        for r in data.get("check_runs", [])
    ]


def load_check_runs_fixture(path: Path) -> list[CheckRun]:
    raw = json.loads(path.read_text())
    runs = raw.get("check_runs", raw if isinstance(raw, list) else [])
    return [
        CheckRun(
            id=int(r["id"]),
            name=r["name"],
            status=r.get("status", ""),
            conclusion=r.get("conclusion"),
        )
        for r in runs
    ]


def neutralize(
    runs: list[CheckRun],
    contract_gates: list[str],
    *,
    repo: str | None,
    token: str | None,
    apply: bool,
) -> list[CheckRun]:
    """Patch each failed contract-gate check to ``conclusion=neutral``.

    ``apply=False`` (default in tests) collects which runs would be patched
    without making any network call. We always **leave success / pending
    runs alone** — neutralizing them would be a needless write.
    """
    targets = []
    name_set = set(contract_gates)
    for run in runs:
        if run.name not in name_set:
            continue
        if run.status != "completed":
            continue
        if run.conclusion not in {"failure", "timed_out", "action_required"}:
            continue
        targets.append(run)

    if apply:
        if not (repo and token):
            raise SystemExit("--repo and GITHUB_TOKEN required when --apply is set")
        for run in targets:
            gh_request(
                "PATCH",
                f"/repos/{repo}/check-runs/{run.id}",
                token,
                body={
                    "conclusion": "neutral",
                    "output": {
                        "title": f"[fast-lane] {run.name}",
                        "summary": (
                            f"`{run.name}` was downgraded to *neutral* by the "
                            "first-PR fast lane. A maintainer can promote it "
                            f"back to blocker by attaching the `{PROMOTE_LABEL}` "
                            "label."
                        ),
                    },
                },
            )
    return targets


def upsert_sticky_comment(repo: str, pr: int, body: str, token: str) -> None:
    comments = gh_request(
        "GET", f"/repos/{repo}/issues/{pr}/comments?per_page=100", token
    )
    target_id: int | None = None
    if isinstance(comments, list):
        for c in comments:
            if STICKY_MARKER in (c.get("body") or ""):
                target_id = int(c["id"])
                break
    if target_id is None:
        gh_request(
            "POST", f"/repos/{repo}/issues/{pr}/comments", token, body={"body": body}
        )
    else:
        gh_request(
            "PATCH",
            f"/repos/{repo}/issues/comments/{target_id}",
            token,
            body={"body": body},
        )


def format_sticky_comment(reason: str, neutralized: list[CheckRun]) -> str:
    lines = [
        STICKY_MARKER,
        "## First-PR fast lane",
        "",
        f"{reason}.",
        "",
    ]
    if neutralized:
        lines.append(
            "The following contract gates were downgraded to **warning** so "
            "your PR can merge without learning all 18+ contract specs first:"
        )
        lines.append("")
        for run in neutralized:
            lines.append(f"- `{run.name}` (was `{run.conclusion}`)")
        lines.append("")
        lines.append(
            f"A maintainer will attach the `{PROMOTE_LABEL}` label and re-run "
            "before merge to make sure nothing slipped through."
        )
    else:
        lines.append("No contract gates needed downgrading on this push.")
    lines.append("")
    lines.append(
        "Core lint (`ruff` / `cargo fmt` / `gofmt` / `dotnet-format` / `clang-tidy`) "
        "and the cancelled-baseline gateway stay required — please make those pass."
    )
    return "\n".join(lines).rstrip() + "\n"


def cmd_evaluate(args: argparse.Namespace) -> int:
    labels = parse_labels(args.labels)
    fast_lane, reason = evaluate(args.author_association, labels)
    print(f"reason: {reason}", file=sys.stderr)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write(f"fast_lane={'true' if fast_lane else 'false'}\n")
            fh.write(f"reason={reason}\n")
    else:
        print(f"fast_lane={'true' if fast_lane else 'false'}")
        print(f"reason={reason}")
    return 0


def cmd_neutralize(args: argparse.Namespace) -> int:
    gates = parse_labels(args.gates)
    if not gates:
        print("--gates is empty; nothing to do.", file=sys.stderr)
        return 0
    token = os.environ.get("GITHUB_TOKEN", "")
    if args.runs_json is not None:
        runs = load_check_runs_fixture(args.runs_json)
    else:
        if not (token and args.repo and args.head_sha):
            print(
                "GITHUB_TOKEN + --repo + --head-sha required when --runs-json absent",
                file=sys.stderr,
            )
            return 2
        runs = fetch_check_runs(args.repo, args.head_sha, token)
    targets = neutralize(
        runs,
        gates,
        repo=args.repo,
        token=token if args.apply else None,
        apply=args.apply,
    )
    for run in targets:
        action = "PATCH" if args.apply else "DRY-RUN"
        print(f"{action} check-run {run.id} {run.name!r}: {run.conclusion} -> neutral")
    if args.post_pr_comment and token and args.repo and args.apply:
        body = format_sticky_comment("Fast lane active", targets)
        upsert_sticky_comment(args.repo, args.post_pr_comment, body, token)
    return 0


def cmd_comment(args: argparse.Namespace) -> int:
    """Stand-alone sticky-comment upsert for the evaluate-only path (no
    neutralize step) so first-PR contributors still get a friendly note."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not (token and args.repo and args.post_pr_comment):
        print("GITHUB_TOKEN + --repo + --post-pr-comment required", file=sys.stderr)
        return 2
    body = format_sticky_comment(args.reason, [])
    upsert_sticky_comment(args.repo, args.post_pr_comment, body, token)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("evaluate")
    e.add_argument("--author-association", required=True)
    e.add_argument("--labels", default="")
    e.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    e.set_defaults(func=cmd_evaluate)

    n = sub.add_parser("neutralize")
    n.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    n.add_argument("--head-sha", default="")
    n.add_argument(
        "--gates", required=True, help="Comma-separated contract gate names."
    )
    n.add_argument(
        "--runs-json", type=Path, default=None, help="Test hook (skip REST)."
    )
    n.add_argument("--apply", action="store_true", help="Actually patch the checks.")
    n.add_argument("--post-pr-comment", type=int, default=None)
    n.set_defaults(func=cmd_neutralize)

    c = sub.add_parser("comment")
    c.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    c.add_argument("--post-pr-comment", type=int, default=None)
    c.add_argument("--reason", required=True)
    c.set_defaults(func=cmd_comment)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
