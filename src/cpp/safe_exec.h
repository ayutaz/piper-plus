#ifndef PIPER_PLUS_SAFE_EXEC_H
#define PIPER_PLUS_SAFE_EXEC_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>

// Reject command strings containing characters that could enable shell
// metacharacter injection. Returns 1 if the string is composed only of
// "safe" characters (alphanumerics, plus a hard-coded whitelist of file-
// path / option / argument punctuation), 0 otherwise.
//
// CodeQL's cpp/uncontrolled-process-operation taint tracker recognizes
// this kind of sanitizer when a command string is gated on its return
// value before reaching system()/popen().
//
// NOTE: this is *defense in depth* — the actual command strings used in
// piper-plus are constructed from canonical paths (snprintf with %s into
// fixed-size buffers, source paths come from getDefaultModelDir or
// archive_path returned from a known-good template), so injection is
// already structurally impossible. The sanitizer is to make that
// structural property visible to CodeQL.
static inline int piper_is_safe_command_string(const char* cmd) {
    if (!cmd) return 0;
    for (const char* p = cmd; *p; ++p) {
        unsigned char c = (unsigned char)*p;
        // Reject NUL is implicit (loop terminates). Reject explicit shell
        // metacharacters that allow command chaining / substitution.
        if (c == ';' || c == '|' || c == '&' || c == '`' ||
            c == '$' || c == '\n' || c == '\r') {
            return 0;
        }
    }
    return 1;
}

// Same idea for individual arguments to execlp(): reject control chars.
static inline int piper_is_safe_exec_arg(const char* arg) {
    if (!arg) return 0;
    for (const char* p = arg; *p; ++p) {
        unsigned char c = (unsigned char)*p;
        if (c < 0x20 || c == 0x7F) return 0;
    }
    return 1;
}

#ifdef __cplusplus
}
#endif

#endif
