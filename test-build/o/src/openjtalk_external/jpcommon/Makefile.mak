
CC = cl

CFLAGS = /O2 /Ob2 /Oi /Ot /Oy /GT /GL /TC /D CHARSET_SHIFT_JIS
LFLAGS = /LTCG

CORES = jpcommon.obj jpcommon_node.obj jpcommon_label.obj

all: jpcommon.lib

jpcommon.lib: $(CORES)
	lib $(LFLAGS) /OUT:$@ $(CORES)

.c.obj:
	$(CC) $(CFLAGS) /c $<

clean:
	del *.lib
	del *.obj
