#!/usr/bin/env python3
"""
Switch between simple and full app based on environment
"""

import os

# Check if we should use the simple version
USE_SIMPLE = os.environ.get("USE_SIMPLE_APP", "true").lower() == "true"

if USE_SIMPLE:
    print("Using simplified app (no models)")
    from app_simple import interface
else:
    print("Using full app with models")
    from app import interface

# Export interface for Gradio
__all__ = ["interface"]