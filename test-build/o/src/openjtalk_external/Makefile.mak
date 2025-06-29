
INSTALLDIR = C:\open_jtalk

all:
	cd text2mecab
	nmake /f Makefile.mak
	cd ..
	cd mecab
	nmake /f Makefile.mak
	cd ..
	cd mecab2njd
	nmake /f Makefile.mak
	cd ..
	cd njd
	nmake /f Makefile.mak
	cd ..
	cd njd_set_pronunciation
	nmake /f Makefile.mak
	cd ..
	cd njd_set_digit
	nmake /f Makefile.mak
	cd ..
	cd njd_set_accent_phrase
	nmake /f Makefile.mak
	cd ..
	cd njd_set_accent_type
	nmake /f Makefile.mak
	cd ..
	cd njd_set_unvoiced_vowel
	nmake /f Makefile.mak
	cd ..
	cd njd_set_long_vowel
	nmake /f Makefile.mak
	cd ..
	cd njd2jpcommon
	nmake /f Makefile.mak
	cd ..
	cd jpcommon
	nmake /f Makefile.mak
	cd ..
	cd bin
	nmake /f Makefile.mak
	cd ..
	cd mecab-naist-jdic
	nmake /f Makefile.mak
	cd ..

clean:
	cd text2mecab
	nmake /f Makefile.mak clean
	cd ..
	cd mecab
	nmake /f Makefile.mak clean
	cd ..
	cd mecab2njd
	nmake /f Makefile.mak clean
	cd ..
	cd njd
	nmake /f Makefile.mak clean
	cd ..
	cd njd_set_pronunciation
	nmake /f Makefile.mak clean
	cd ..
	cd njd_set_digit
	nmake /f Makefile.mak clean
	cd ..
	cd njd_set_accent_phrase
	nmake /f Makefile.mak clean
	cd ..
	cd njd_set_accent_type
	nmake /f Makefile.mak clean
	cd ..
	cd njd_set_unvoiced_vowel
	nmake /f Makefile.mak clean
	cd ..
	cd njd_set_long_vowel
	nmake /f Makefile.mak clean
	cd ..
	cd njd2jpcommon
	nmake /f Makefile.mak clean
	cd ..
	cd jpcommon
	nmake /f Makefile.mak clean
	cd ..
	cd bin
	nmake /f Makefile.mak clean
	cd ..
	cd mecab-naist-jdic
	nmake /f Makefile.mak clean
	cd ..

install::
	@if not exist "$(INSTALLDIR)\bin" mkdir "$(INSTALLDIR)\bin"
	cd bin
	copy *.exe $(INSTALLDIR)\bin
	cd ..
	@if not exist "$(INSTALLDIR)\dic" mkdir "$(INSTALLDIR)\dic"
	cd mecab-naist-jdic
	copy char.bin $(INSTALLDIR)\dic
	copy matrix.bin $(INSTALLDIR)\dic
	copy sys.dic $(INSTALLDIR)\dic
	copy unk.dic $(INSTALLDIR)\dic
	copy left-id.def $(INSTALLDIR)\dic
	copy right-id.def $(INSTALLDIR)\dic
	copy rewrite.def $(INSTALLDIR)\dic
	copy pos-id.def $(INSTALLDIR)\dic
	cd ..
