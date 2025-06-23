#!/bin/bash
set -e

cd "$1/src"
make install

# Copy all necessary headers
mkdir -p "$2/include"
cp text2mecab/text2mecab.h "$2/include/"
cp mecab/src/mecab.h "$2/include/"
cp njd/njd.h "$2/include/"
cp jpcommon/jpcommon.h "$2/include/"
cp njd_set_pronunciation/njd_set_pronunciation.h "$2/include/"
cp njd_set_digit/njd_set_digit.h "$2/include/"
cp njd_set_accent_phrase/njd_set_accent_phrase.h "$2/include/"
cp njd_set_accent_type/njd_set_accent_type.h "$2/include/"
cp njd_set_unvoiced_vowel/njd_set_unvoiced_vowel.h "$2/include/"
cp njd_set_long_vowel/njd_set_long_vowel.h "$2/include/"
cp mecab2njd/mecab2njd.h "$2/include/"
cp njd2jpcommon/njd2jpcommon.h "$2/include/"

# Copy all necessary libraries
mkdir -p "$2/lib"
cp text2mecab/libtext2mecab.a "$2/lib/"
cp mecab/src/libmecab.a "$2/lib/"
cp njd/libnjd.a "$2/lib/"
cp jpcommon/libjpcommon.a "$2/lib/"
cp njd_set_pronunciation/libnjd_set_pronunciation.a "$2/lib/"
cp njd_set_digit/libnjd_set_digit.a "$2/lib/"
cp njd_set_accent_phrase/libnjd_set_accent_phrase.a "$2/lib/"
cp njd_set_accent_type/libnjd_set_accent_type.a "$2/lib/"
cp njd_set_unvoiced_vowel/libnjd_set_unvoiced_vowel.a "$2/lib/"
cp njd_set_long_vowel/libnjd_set_long_vowel.a "$2/lib/"
cp mecab2njd/libmecab2njd.a "$2/lib/"
cp njd2jpcommon/libnjd2jpcommon.a "$2/lib/"