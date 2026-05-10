#!/usr/bin/env bash
# Build a TAR archive of an OpenJTalk dictionary plus a SHA-256 sidecar so
# Android consumers can fetch it via DictionaryDownloader.downloadFromHuggingFace.
#
# Usage:
#   tools/build-openjtalk-dict-archive.sh <SRC_DICT_DIR> [OUT_DIR]
#
# Produces under OUT_DIR (default = ./dist/open_jtalk_dic):
#   open_jtalk_dic.tar
#   open_jtalk_dic.tar.sha256
#
# These two files are what the Hugging Face Hub repo
# (`ayousanz/piper-plus-base`) hosts at /resolve/main/<file>. The downloader
# pulls both, verifies the SHA-256 against the sidecar, and extracts the
# archive into `Context.filesDir/open_jtalk_dic/`.
#
# Requirements: bash 4+, GNU tar (`--format=ustar`), sha256sum.

set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 <SRC_DICT_DIR> [OUT_DIR]" >&2
    exit 64
fi

SRC_DICT="$(realpath "$1")"
OUT_DIR="${2:-./dist/open_jtalk_dic}"
mkdir -p "$OUT_DIR"
OUT_DIR="$(realpath "$OUT_DIR")"

if [ ! -d "$SRC_DICT" ]; then
    echo "ERROR: source directory does not exist: $SRC_DICT" >&2
    exit 65
fi

# Sanity-check: the standard mecab-naist-jdic distribution always ships
# sys.dic and unk.dic. If they're missing we likely have a stripped or
# wrong-format dictionary; bail rather than ship a half-broken archive.
for required in sys.dic unk.dic; do
    if [ ! -f "$SRC_DICT/$required" ]; then
        echo "ERROR: $SRC_DICT is missing $required — not an OpenJTalk dict?" >&2
        exit 66
    fi
done

ARCHIVE="$OUT_DIR/open_jtalk_dic.tar"
SHA_FILE="$OUT_DIR/open_jtalk_dic.tar.sha256"

# Tar is rooted at the dict directory itself so the archive expands as
# `open_jtalk_dic/<files>` on the consumer side — matching what
# DictionaryDownloader expects after extraction.
PARENT="$(dirname  "$SRC_DICT")"
DIR_NAME="$(basename "$SRC_DICT")"

echo "[*] Packing $SRC_DICT → $ARCHIVE"
tar --format=ustar \
    --owner=0 --group=0 --numeric-owner \
    --sort=name \
    --mtime='UTC 1970-01-01' \
    -C "$PARENT" -cf "$ARCHIVE" "$DIR_NAME"

echo "[*] Computing SHA-256 sidecar"
( cd "$OUT_DIR" && sha256sum "$(basename "$ARCHIVE")" > "$(basename "$SHA_FILE")" )

echo
echo "Archive : $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
echo "SHA-256 : $SHA_FILE"
echo
echo "Upload both files to the HF Hub repo (e.g. ayousanz/piper-plus-base)"
echo "under /resolve/main/. Android consumers will then fetch via"
echo "DictionaryDownloader.downloadFromHuggingFace()."
