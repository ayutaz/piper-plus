"""Three-category classification of fenced code blocks (T-009).

A block is one of:

* ``executable`` — no placeholder, no skip directive, no environment
  dependency. The execution gate (T-010) is allowed to run it.
* ``needs_placeholder`` — at least one placeholder pattern matches. The
  block is template content; running it verbatim is meaningless or
  unsafe (e.g. would target localhost with a placeholder URL).
* ``skip_warranted`` — explicit skip directive on the first non-blank
  line, OR the body matches one of the environment-dependency patterns
  the sandbox cannot satisfy. ``skip_warranted`` also covers unknown
  languages so they don't silently default into ``executable``.

The classifier is deterministic and side-effect-free; it consumes the
fields from :class:`extractor.FencedBlock` plus a config loaded from
``docs/spec/doc-examples-contract.toml``.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


CATEGORY_EXECUTABLE = "executable"
CATEGORY_NEEDS_PLACEHOLDER = "needs_placeholder"
CATEGORY_SKIP_WARRANTED = "skip_warranted"


@dataclass(frozen=True)
class Classification:
    """Result of classifying one block.

    Attributes:
        category: One of the ``CATEGORY_*`` constants.
        placeholders_detected: Distinct placeholder tokens that matched.
        directives_detected: Skip directives that matched.
        env_dependencies: Substrings/regex names that matched.
        suggested_action: Free-form hint passed through to the JSON
            output so reviewers see what the script recommends.
    """

    category: str
    placeholders_detected: list[str]
    directives_detected: list[str]
    env_dependencies: list[str]
    suggested_action: str


@dataclass(frozen=True)
class ClassifierConfig:
    canonical_languages: frozenset[str]
    language_aliases: dict[str, str]
    placeholder_patterns: list[re.Pattern[str]]
    skip_directive_patterns: list[re.Pattern[str]]
    env_dependency_patterns: list[str]


def load_config(toml_path: Path) -> ClassifierConfig:
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    languages = data.get("languages", {})
    canonical = frozenset(languages.get("canonical", []))
    aliases_raw = languages.get("aliases", {})
    aliases = {alias.lower(): canon for alias, canon in aliases_raw.items()}

    placeholder_cfg = data.get("placeholders", {})
    placeholders = [re.compile(pat) for pat in placeholder_cfg.get("patterns", [])]

    skip_cfg = data.get("skip_directives", {})
    skip_patterns = [re.compile(pat) for pat in skip_cfg.get("patterns", [])]

    env_cfg = data.get("env_dependencies", {})
    env_patterns = list(env_cfg.get("patterns", []))

    return ClassifierConfig(
        canonical_languages=canonical,
        language_aliases=aliases,
        placeholder_patterns=placeholders,
        skip_directive_patterns=skip_patterns,
        env_dependency_patterns=env_patterns,
    )


def normalize_language(raw: str, config: ClassifierConfig) -> str:
    """Map a raw info-string language to the canonical name, or ``""``.

    Returns ``""`` (empty) for unknown or absent languages — the
    classifier then routes them to ``skip_warranted``.
    """
    low = raw.lower().strip()
    if not low:
        return ""
    if low in config.canonical_languages:
        return low
    if low in config.language_aliases:
        return config.language_aliases[low]
    return ""  # unknown → skip


def _first_nonblank_line(body: str) -> str:
    for line in body.splitlines():
        if line.strip():
            return line
    return ""


def _detect_placeholders(body: str, patterns: list[re.Pattern[str]]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for m in pat.finditer(body):
            token = m.group(0)
            if token not in seen:
                seen.add(token)
                found.append(token)
    return found


def _detect_directives(body: str, patterns: list[re.Pattern[str]]) -> list[str]:
    head = _first_nonblank_line(body)
    return [pat.pattern for pat in patterns if pat.search(head)]


def _detect_env_deps(body: str, patterns: list[str]) -> list[str]:
    return [pat for pat in patterns if pat in body]


def classify(
    *,
    language: str,
    body: str,
    config: ClassifierConfig,
) -> Classification:
    """Classify a single block.

    The precedence is:

    1. Explicit skip directive → ``skip_warranted``.
    2. Unknown / absent language → ``skip_warranted`` (``unknown_language``).
    3. Environment-dependency pattern hit → ``skip_warranted``.
    4. Placeholder pattern hit → ``needs_placeholder``.
    5. Otherwise → ``executable``.

    Steps 1–3 win over placeholders so a directive-tagged block carrying
    a placeholder doesn't get downgraded to placeholder.
    """
    normalized_lang = normalize_language(language, config)

    directives = _detect_directives(body, config.skip_directive_patterns)
    if directives:
        return Classification(
            category=CATEGORY_SKIP_WARRANTED,
            placeholders_detected=[],
            directives_detected=directives,
            env_dependencies=[],
            suggested_action="respect_skip_directive",
        )

    if not normalized_lang:
        return Classification(
            category=CATEGORY_SKIP_WARRANTED,
            placeholders_detected=[],
            directives_detected=["unknown_language"],
            env_dependencies=[],
            suggested_action="route_via_language_alias_table",
        )

    env_deps = _detect_env_deps(body, config.env_dependency_patterns)
    if env_deps:
        return Classification(
            category=CATEGORY_SKIP_WARRANTED,
            placeholders_detected=[],
            directives_detected=[],
            env_dependencies=env_deps,
            suggested_action="sandbox_cannot_satisfy_env_dep",
        )

    placeholders = _detect_placeholders(body, config.placeholder_patterns)
    if placeholders:
        return Classification(
            category=CATEGORY_NEEDS_PLACEHOLDER,
            placeholders_detected=placeholders,
            directives_detected=[],
            env_dependencies=[],
            suggested_action="wrap_with_doctest_skip_until_t011",
        )

    return Classification(
        category=CATEGORY_EXECUTABLE,
        placeholders_detected=[],
        directives_detected=[],
        env_dependencies=[],
        suggested_action="execution_gate_candidate",
    )
