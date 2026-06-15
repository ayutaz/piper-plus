"""Unit tests for ``scripts/check_*.py`` CI gate helpers.

This namespace hosts the pytest modules that exercise the
``scripts/check_*.py`` regression-guard scripts (AI-15 and friends).
Tests here are intentionally lightweight: AST walks, JSON pin diffing,
markdown parsing — never model inference or training side-effects.
"""
