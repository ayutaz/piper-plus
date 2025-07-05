#!/bin/bash
# Apply patches for open_jtalk_phonemizer

set -e

# Add open_jtalk_phonemizer to Makefile.am
sed -i.bak 's/^bin_PROGRAMS = open_jtalk$/bin_PROGRAMS = open_jtalk open_jtalk_phonemizer/' bin/Makefile.am

# Add build rules to Makefile.am
cat >> bin/Makefile.am << 'EOF'

open_jtalk_phonemizer_SOURCES = open_jtalk_phonemizer.c
open_jtalk_phonemizer_CFLAGS = @AM_CFLAGS@ @HTSENGINE_CFLAGS@
open_jtalk_phonemizer_LDADD = ../text2mecab/libtext2mecab.la \
	../mecab2njd/libmecab2njd.la \
	../njd_set_pronunciation/libnjd_set_pronunciation.la \
	../njd_set_digit/libnjd_set_digit.la \
	../njd_set_accent_phrase/libnjd_set_accent_phrase.la \
	../njd_set_accent_type/libnjd_set_accent_type.la \
	../njd_set_unvoiced_vowel/libnjd_set_unvoiced_vowel.la \
	../njd_set_long_vowel/libnjd_set_long_vowel.la \
	../njd2jpcommon/libnjd2jpcommon.la \
	../jpcommon/libjpcommon.la \
	../mecab/src/libmecab.la \
	../njd/libnjd.la \
	@HTSENGINE_LIBS@
EOF

# Regenerate Makefile.in
automake bin/Makefile || true