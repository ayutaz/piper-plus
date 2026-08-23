"""TEMPORARY probe for the distroless `import onnxruntime` SIGSEGV (exit 139).

Run inside the final stage via stdin, because distroless has no shell:

    docker run --rm -i --entrypoint /usr/bin/python3 <image> - < _probe_distroless.py

Delete once the root cause is fixed.
"""

import ctypes
import ctypes.util
import faulthandler
import glob
import os
import platform
import sys


faulthandler.enable()

print("=== interpreter ===", flush=True)
print("version :", sys.version.replace("\n", " "), flush=True)
print("exec    :", sys.executable, flush=True)
print("prefix  :", sys.prefix, flush=True)
print("machine :", platform.machine(), flush=True)
print("libc    :", platform.libc_ver(), flush=True)
print("path    :", sys.path, flush=True)

print("=== stdlib dirs ===", flush=True)
for d in ("/usr/lib/python3.13", "/usr/local/lib/python3.13"):
    print(" ", d, "exists" if os.path.isdir(d) else "MISSING", flush=True)
for d in ("/usr/lib/python3.13/lib-dynload", "/usr/local/lib/python3.13/lib-dynload"):
    n = len(glob.glob(d + "/*.so")) if os.path.isdir(d) else -1
    print(" ", d, f"{n} .so", flush=True)

print("=== shared libs ===", flush=True)
for name in ("stdc++", "gomp", "gcc_s", "m", "pthread", "dl", "rt", "sndfile"):
    print(f"  find_library({name}) ->", ctypes.util.find_library(name), flush=True)
for pat in (
    "/usr/lib/libstdc++*",
    "/usr/lib/*/libstdc++*",
    "/usr/lib/libgomp*",
    "/usr/lib/*/libgomp*",
    "/usr/lib/*/libgcc_s*",
):
    print(" ", pat, "->", glob.glob(pat), flush=True)

print("=== onnxruntime layout ===", flush=True)
sos = sorted(
    glob.glob("/usr/local/lib/python3.13/site-packages/onnxruntime/capi/*.so")
) + sorted(glob.glob("/usr/local/lib/python3.13/site-packages/onnxruntime*/**/*.so", recursive=True))
for so in dict.fromkeys(sos):
    print("  so:", so, os.path.getsize(so), flush=True)

print("=== dlopen native modules directly ===", flush=True)
for so in dict.fromkeys(sos):
    try:
        ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
        print("  CDLL OK  ", so, flush=True)
    except OSError as exc:
        print("  CDLL FAIL", so, "->", exc, flush=True)

print("=== import onnxruntime (may crash) ===", flush=True)
import onnxruntime as ort  # noqa: E402

print("imported OK:", ort.__version__, flush=True)
print("providers:", ort.get_available_providers(), flush=True)
