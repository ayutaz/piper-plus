// Argv-based process execution helpers — replace shell-based system()/popen()
// to eliminate cpp/command-line-injection and cpp/uncontrolled-process-operation
// alerts (CodeQL). Each argv element is passed verbatim to the spawned process,
// so shell metacharacters (;, &, |, `, $, etc.) cannot be interpreted.
//
// POSIX: posix_spawnp + waitpid / pipe + posix_spawn for output capture
// Win32: _spawnvp / _popen wrapper that does NOT invoke cmd.exe parsing
//
// Skip on Apple-embedded (iOS / tvOS / watchOS) — App Sandbox forbids
// process spawning. The header is still safely #included so that callers
// can guard at the call site.

#ifndef PIPER_PROC_EXEC_H
#define PIPER_PROC_EXEC_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Run argv[0] with the given argv (NULL-terminated). Returns the child's exit
// status (0 on success), or -1 on spawn / wait failure.
//
// argv MUST be NULL-terminated. argv[0] is the program name; on POSIX it is
// resolved through PATH (posix_spawnp); on Windows _spawnvp does the same.
int piper_run_argv(const char* const argv[]);

// Same as piper_run_argv but captures the child's stdout into `out_buf` (up
// to `out_size - 1` bytes, null-terminated). Returns 0 on success, -1 on
// spawn / pipe / wait failure or if the child exited with non-zero status.
//
// `bytes_read` (out) receives the number of bytes captured (excluding the
// trailing NUL). Pass NULL if you don't care.
int piper_capture_argv(const char* const argv[],
                       char* out_buf,
                       size_t out_size,
                       size_t* bytes_read);

// Whether the current platform supports process spawning at all. Returns 0
// on Apple-embedded (App Sandbox) and 1 elsewhere. Callers can short-circuit
// with this to keep the code path identical between platforms.
int piper_proc_exec_supported(void);

#ifdef __cplusplus
}
#endif

#endif // PIPER_PROC_EXEC_H
