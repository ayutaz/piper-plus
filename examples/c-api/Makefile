# Build with: PKG_CONFIG_PATH=/path/to/lib/pkgconfig make
CC      ?= gcc
CFLAGS  ?= -std=c99 -Wall -Wextra -O2
PKG_CFLAGS := $(shell pkg-config --cflags piper_plus 2>/dev/null)
PKG_LIBS   := $(shell pkg-config --libs piper_plus 2>/dev/null)

TARGETS = basic streaming multi_language

all: $(TARGETS)

basic: basic.c
	$(CC) $(CFLAGS) $(PKG_CFLAGS) -o $@ $< $(PKG_LIBS)

streaming: streaming.c
	$(CC) $(CFLAGS) $(PKG_CFLAGS) -o $@ $< $(PKG_LIBS)

multi_language: multi_language.c
	$(CC) $(CFLAGS) $(PKG_CFLAGS) -o $@ $< $(PKG_LIBS)

clean:
	rm -f $(TARGETS)

.PHONY: all clean
