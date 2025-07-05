#!/bin/bash
# Apply patches for open_jtalk_phonemizer

set -e

# Don't modify Makefile.am to avoid automake requirement
# Instead, we'll add the phonemizer after the main build