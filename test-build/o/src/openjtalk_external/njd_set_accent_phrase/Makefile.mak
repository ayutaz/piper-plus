
CC = cl

CFLAGS = /O2 /Ob2 /Oi /Ot /Oy /GT /GL /TC /I ../njd /D CHARSET_SHIFT_JIS
LFLAGS = /LTCG

CORES = njd_set_accent_phrase.obj

all: njd_set_accent_phrase.lib

njd_set_accent_phrase.lib: $(CORES)
	lib $(LFLAGS) /OUT:$@ $(CORES)

.c.obj:
	$(CC) $(CFLAGS) /c $<

clean:
	del *.lib
	del *.obj
