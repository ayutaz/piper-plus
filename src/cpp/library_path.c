/* _GNU_SOURCE is required on Linux for dladdr() and Dl_info in <dlfcn.h>.
 * Must be defined before any system header. */
#if !defined(_WIN32) && !defined(_WIN64) && !defined(__APPLE__)
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#endif

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

/* Strip the filename from a full path, leaving only the directory.
 * Modifies the buffer in place. Returns 0 on success, -1 on failure. */
static int strip_filename(char *path) {
    char *last_sep = strrchr(path, '\\');
    if (!last_sep) last_sep = strrchr(path, '/');
    if (!last_sep) return -1;
    *last_sep = '\0';
    return 0;
}

int piper_plus_get_exe_dir(char *buf, int size) {
    if (!buf || size <= 0) return -1;

    wchar_t wpath[MAX_PATH];
    DWORD len = GetModuleFileNameW(NULL, wpath, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) return -1;

    /* Convert to UTF-8 */
    int needed = WideCharToMultiByte(CP_UTF8, 0, wpath, -1, NULL, 0, NULL, NULL);
    if (needed <= 0 || needed > size) return -1;

    WideCharToMultiByte(CP_UTF8, 0, wpath, -1, buf, size, NULL, NULL);

    return strip_filename(buf);
}

#else /* Unix (Linux, macOS) */

#include <dlfcn.h>
#include <libgen.h>
#include <stdlib.h>

#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <limits.h>
#else
#include <unistd.h>
#include <limits.h>
#endif

int piper_plus_get_library_dir(char *buf, int size) {
    if (!buf || size <= 0) return -1;

    Dl_info info;
    if (!dladdr((void *)piper_plus_get_library_dir, &info)) return -1;
    if (!info.dli_fname) return -1;

    /* realpath with NULL: POSIX.1-2008 dynamic allocation (no fixed buffer) */
    char *resolved = realpath(info.dli_fname, NULL);
    if (!resolved) {
        /* Fallback: copy dli_fname for dirname (which may modify its argument) */
        size_t fname_len = strlen(info.dli_fname);
        resolved = (char *)malloc(fname_len + 1);
        if (!resolved) return -1;
        memcpy(resolved, info.dli_fname, fname_len + 1);
    }

    /* dirname may modify its argument or return a pointer into it —
     * 'resolved' is our own heap buffer so this is safe. */
    char *dir = dirname(resolved);
    if (!dir) { free(resolved); return -1; }

    int dir_len = (int)strlen(dir);
    if (dir_len >= size) { free(resolved); return -1; }

    memcpy(buf, dir, dir_len);
    buf[dir_len] = '\0';
    free(resolved);
    return 0;
}

int piper_plus_get_exe_dir(char *buf, int size) {
    if (!buf || size <= 0) return -1;

    char *resolved = NULL;

#ifdef __APPLE__
    {
        /* First call to get required buffer size */
        uint32_t pathsize = 0;
        _NSGetExecutablePath(NULL, &pathsize);

        char *rawpath = (char *)malloc(pathsize);
        if (!rawpath) return -1;
        if (_NSGetExecutablePath(rawpath, &pathsize) != 0) {
            free(rawpath);
            return -1;
        }

        /* realpath with NULL: dynamic allocation */
        resolved = realpath(rawpath, NULL);
        if (!resolved) {
            /* Fallback: use raw path (already heap-allocated) */
            resolved = rawpath;
        } else {
            free(rawpath);
        }
    }
#else
    {
        /* Linux: readlink /proc/self/exe
         * Use a dynamically-sized buffer in case PATH_MAX is insufficient. */
        size_t bufsize = 4096;
#ifdef PATH_MAX
        if ((size_t)PATH_MAX > bufsize) bufsize = (size_t)PATH_MAX;
#endif
        char *linkbuf = (char *)malloc(bufsize);
        if (!linkbuf) return -1;

        ssize_t len = readlink("/proc/self/exe", linkbuf, bufsize - 1);
        if (len <= 0) { free(linkbuf); return -1; }
        linkbuf[len] = '\0';

        /* realpath with NULL: dynamic allocation */
        resolved = realpath(linkbuf, NULL);
        if (!resolved) {
            /* Fallback: use linkbuf directly */
            resolved = linkbuf;
        } else {
            free(linkbuf);
        }
    }
#endif

    /* dirname may modify its argument — 'resolved' is our own heap buffer */
    char *dir = dirname(resolved);
    if (!dir) { free(resolved); return -1; }

    int dir_len = (int)strlen(dir);
    if (dir_len >= size) { free(resolved); return -1; }

    memcpy(buf, dir, dir_len);
    buf[dir_len] = '\0';
    free(resolved);
    return 0;
}

#endif
