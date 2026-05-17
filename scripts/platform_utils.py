#!/usr/bin/env python3
"""
Common platform-related utilities and constants.
"""

import sys


# Platform name mapping for consistent naming across scripts
PLATFORM_NAMES = {"linux": "ubuntu", "darwin": "macos", "win32": "windows"}

# Platform icons for display
PLATFORM_ICONS = {"linux": "🐧", "darwin": "🍎", "win32": "🪟"}


def get_platform_name() -> str:
    """Get the current platform name for display."""
    return PLATFORM_NAMES.get(sys.platform, sys.platform)


def get_platform_icon() -> str:
    """Get the current platform icon."""
    return PLATFORM_ICONS.get(sys.platform, "💻")


def force_utf8_output() -> None:
    """Reconfigure stdout/stderr to UTF-8 so gate scripts run on any console.

    Gate scripts print non-ASCII status glyphs (—, ✓, ↔, ≥). On Windows the
    console codepage (e.g. cp932 on Japanese Windows, cp1252 on US) cannot
    encode them and ``print()`` raises UnicodeEncodeError, crashing the
    script instead of reporting its result (QA finding F6).

    Call this once at module import time, before any ``print()``. It is a
    no-op when the stream is already UTF-8 or cannot be reconfigured.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            # Stream is already UTF-8, detached, or backed by a console that
            # rejects reconfiguration — keeping the original encoding is the
            # safe fallback, so the failure is intentionally swallowed.
            pass
