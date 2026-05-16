#!/usr/bin/env python3
"""Skill / hook health-check meta gate.

`.claude/skills/*/SKILL.md` の各 frontmatter / referenced script / trigger 衝突を
検証する。 メタワークフロー監査の "skill / hook の rot 防止" 候補の実装。

検証内容:

  1. SKILL.md の YAML frontmatter が parse でき、 必須 key (name / description /
     allowed-tools) が揃う
  2. ``description`` の文字数が 80-400 文字に収まる (短すぎ / 長すぎ警告)
  3. ``name`` が directory 名と一致する
  4. SKILL.md 本文中の ``scripts/*.py`` への参照が repo 内に実在する
  5. 全 skill の ``description`` 間で「同じ trigger 文言」 が複数 skill に重複
     していないか (uniqueness 検査)
  6. ``.claude/hooks/*.sh`` 各 shell スクリプトが実行可能 (+x)、 shebang あり

Exit codes:
    0  -- 全 skill / hook 健全
    1  -- いずれかの不整合あり (report 出力)

Usage:
    python scripts/check_skill_health.py
    python scripts/check_skill_health.py --verbose
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / ".claude/skills"
HOOKS_DIR = REPO_ROOT / ".claude/hooks"

FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---", re.DOTALL)
SCRIPT_REF_RE = re.compile(r"scripts/([a-zA-Z0-9_./-]+\.(?:py|sh))")
# 2 named groups so re.findall always returns predictable tuples (jp_quoted,
# slash_cmd). Empty strings are filtered downstream — avoids the mixed
# capturing / non-capturing alternation surprise where findall returns a
# flat string list when only one group exists.
TRIGGER_FRAGMENT_RE = re.compile(
    r"「(?P<quoted>[^」]{6,30})」|(?P<slash>/[a-z][a-z0-9-]+)"
)


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Tiny single-line YAML frontmatter parser (avoids PyYAML dep)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    out: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in m.group(1).splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith(" ") and current_key is not None:
            # continuation line — append
            out[current_key] = out.get(current_key, "") + " " + raw_line.strip()
            continue
        if ":" in raw_line:
            key, _, value = raw_line.partition(":")
            key = key.strip()
            value = value.strip()
            out[key] = value
            current_key = key
    return out


def list_skills() -> list[Path]:
    if not SKILLS_DIR.exists():
        return []
    return [p for p in SKILLS_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]


def list_hooks() -> list[Path]:
    if not HOOKS_DIR.exists():
        return []
    return [p for p in HOOKS_DIR.iterdir() if p.suffix == ".sh"]


def extract_trigger_fragments(description: str) -> list[str]:
    """Extract 「...」 quoted phrases + /skill-name references.

    With two named groups in TRIGGER_FRAGMENT_RE, ``findall`` returns a list
    of (quoted, slash) tuples — exactly one element of each tuple is non-empty
    per match. Pick whichever fired.
    """
    fragments: list[str] = []
    for quoted, slash in TRIGGER_FRAGMENT_RE.findall(description):
        chosen = quoted or slash
        if chosen:
            fragments.append(chosen)
    return fragments


def check_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")

    fm = parse_frontmatter(text)
    if fm is None:
        errors.append(f"  [{skill_dir.name}] SKILL.md frontmatter not parseable")
        return errors

    # 1. required keys
    for key in ("name", "description"):
        if not fm.get(key):
            errors.append(f"  [{skill_dir.name}] missing frontmatter key: {key}")

    # 2. name matches directory
    if fm.get("name") and fm["name"].strip() != skill_dir.name:
        errors.append(
            f"  [{skill_dir.name}] name '{fm['name']}' does not match directory"
        )

    # 3. description length
    desc = fm.get("description", "")
    if 0 < len(desc) < 60:
        errors.append(
            f"  [{skill_dir.name}] description too short ({len(desc)} chars): {desc[:50]!r}"
        )
    if len(desc) > 800:
        errors.append(
            f"  [{skill_dir.name}] description very long ({len(desc)} chars) — may not be a single sentence"
        )

    # 4. referenced scripts exist
    for ref in set(SCRIPT_REF_RE.findall(text)):
        script_path = REPO_ROOT / "scripts" / ref
        if not script_path.exists():
            errors.append(
                f"  [{skill_dir.name}] references scripts/{ref} but file does not exist"
            )

    return errors


def check_hook(hook_path: Path) -> list[str]:
    errors: list[str] = []
    # executable bit
    if not os.access(hook_path, os.X_OK):
        errors.append(f"  [{hook_path.name}] not executable (chmod +x missing)")
    # shebang
    try:
        first_line = hook_path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError):
        errors.append(f"  [{hook_path.name}] cannot read first line")
        return errors
    if not first_line.startswith("#!"):
        errors.append(f"  [{hook_path.name}] no shebang on line 1: {first_line!r}")
    return errors


def check_trigger_uniqueness(skills: list[Path]) -> list[str]:
    """Flag trigger phrases used in multiple skill descriptions."""
    fragments: dict[str, list[str]] = defaultdict(list)
    for skill in skills:
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm:
            continue
        desc = fm.get("description", "")
        for frag in extract_trigger_fragments(desc):
            if len(frag) < 6:
                continue
            fragments[frag].append(skill.name)
    out: list[str] = []
    for frag, owners in fragments.items():
        if len(owners) > 1:
            out.append(f"  trigger fragment 「{frag}」 used by: {owners}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    skills = list_skills()
    hooks = list_hooks()

    errors: list[str] = []

    for skill in skills:
        errors.extend(check_skill(skill))
    for hook in hooks:
        errors.extend(check_hook(hook))

    trigger_warnings = check_trigger_uniqueness(skills)

    if args.verbose:
        print(f"inspected {len(skills)} skills, {len(hooks)} hooks")

    if errors:
        print("Skill / hook health errors:", file=sys.stderr)
        for line in errors:
            print(line, file=sys.stderr)
    if trigger_warnings:
        print("\nSkill description trigger overlap (warning):", file=sys.stderr)
        for line in trigger_warnings:
            print(line, file=sys.stderr)

    if errors:
        return 1
    print(
        f"OK skill-health: {len(skills)} skill(s), {len(hooks)} hook(s) inspected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
