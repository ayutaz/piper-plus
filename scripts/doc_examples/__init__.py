"""Doc examples audit module (T-009).

Sub-modules:
- ``extractor``: GFM fenced-block extraction via markdown-it-py.
- ``classifier``: 3-category (executable / needs_placeholder /
  skip_warranted) classification.

The top-level CLI is ``scripts/check_doc_examples.py``; this package is
the implementation backing it.
"""
