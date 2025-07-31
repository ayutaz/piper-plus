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
