
EXTRA_DIST = Makefile.mak

DISTCLEANFILES = *.log *.out *~

MAINTAINERCLEANFILES = Makefile.in

AM_CPPFLAGS = -I @top_srcdir@/text2mecab \
              -I @top_srcdir@/mecab/src \
              -I @top_srcdir@/mecab2njd \
              -I @top_srcdir@/njd \
              -I @top_srcdir@/njd_set_pronunciation \
              -I @top_srcdir@/njd_set_digit \
              -I @top_srcdir@/njd_set_accent_phrase \
              -I @top_srcdir@/njd_set_accent_type \
              -I @top_srcdir@/njd_set_unvoiced_vowel \
              -I @top_srcdir@/njd_set_long_vowel \
              -I @top_srcdir@/njd2jpcommon \
              -I @top_srcdir@/jpcommon \
              -I @HTS_ENGINE_HEADER_DIR@

bin_PROGRAMS = open_jtalk

open_jtalk_LDADD = @top_srcdir@/text2mecab/libtext2mecab.a \
                   @top_srcdir@/mecab/src/libmecab.a \
                   @top_srcdir@/mecab2njd/libmecab2njd.a \
                   @top_srcdir@/njd/libnjd.a \
                   @top_srcdir@/njd_set_pronunciation/libnjd_set_pronunciation.a \
                   @top_srcdir@/njd_set_digit/libnjd_set_digit.a \
                   @top_srcdir@/njd_set_accent_phrase/libnjd_set_accent_phrase.a \
                   @top_srcdir@/njd_set_accent_type/libnjd_set_accent_type.a \
                   @top_srcdir@/njd_set_unvoiced_vowel/libnjd_set_unvoiced_vowel.a \
                   @top_srcdir@/njd_set_long_vowel/libnjd_set_long_vowel.a \
                   @top_srcdir@/njd2jpcommon/libnjd2jpcommon.a \
                   @top_srcdir@/jpcommon/libjpcommon.a \
                   @HTS_ENGINE_LIBRARY@ -lstdc++

open_jtalk_SOURCES = open_jtalk.c
