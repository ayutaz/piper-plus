#include "library_path.h"
#include <string.h>

#if defined(_WIN32) || defined(_WIN64)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static HMODULE get_self_module(void) {
    HMODULE hm = NULL;
    GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        (LPCSTR)&piper_plus_get_library_dir,
        &hm);
    return hm;
}

int piper_plus_get_library_dir(char *buf, int size) {
    if (!buf || size <= 0) return -1;

    HMODULE hm = get_self_module();
    if (!hm) return -1;

    char path[MAX_PATH];
    DWORD len = GetModuleFileNameA(hm, path, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) return -1;

    /* Find last backslash */
    char *last_sep = strrchr(path, '\\');
    if (!last_sep) last_sep = strrchr(path, '/');
    if (!last_sep) return -1;

    int dir_len = (int)(last_sep - path);
    if (dir_len >= size) return -1;

    memcpy(buf, path, dir_len);
    buf[dir_len] = '\0';
    return 0;
}

#else /* Unix (Linux, macOS) */

#include <dlfcn.h>
#include <libgen.h>
#include <stdlib.h>

int piper_plus_get_library_dir(char *buf, int size) {
    if (!buf || size <= 0) return -1;

    Dl_info info;
    if (!dladdr((void *)piper_plus_get_library_dir, &info)) return -1;
    if (!info.dli_fname) return -1;

    /* realpath to resolve symlinks */
    char resolved[4096];
    if (!realpath(info.dli_fname, resolved)) {
        /* Fallback: use dli_fname directly */
        strncpy(resolved, info.dli_fname, sizeof(resolved) - 1);
        resolved[sizeof(resolved) - 1] = '\0';
    }

    /* dirname modifies its argument, so make a copy */
    char *dir = dirname(resolved);
    if (!dir) return -1;

    int dir_len = (int)strlen(dir);
    if (dir_len >= size) return -1;

    memcpy(buf, dir, dir_len);
    buf[dir_len] = '\0';
    return 0;
}

#endif
