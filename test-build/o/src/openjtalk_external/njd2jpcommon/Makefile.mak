
CC = cl

CFLAGS = /O2 /Ob2 /Oi /Ot /Oy /GT /GL /TC /I ../njd /I ../jpcommon /D CHARSET_SHIFT_JIS
LFLAGS = /LTCG

CORES = njd2jpcommon.obj

all: njd2jpcommon.lib

njd2jpcommon.lib: $(CORES)
	lib $(LFLAGS) /OUT:$@ $(CORES)

.c.obj:
	$(CC) $(CFLAGS) /c $<

clean:
	del *.lib
	del *.obj
