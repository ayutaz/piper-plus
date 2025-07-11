#ifndef OPENJTALK_SECURITY_H
#define OPENJTALK_SECURITY_H

#include <stddef.h>  // for size_t

#ifdef __cplusplus
extern "C" {
#endif

// Security functions for OpenJTalk wrapper

// Check if a path is safe (no command injection characters)
int openjtalk_is_safe_path(const char* path);

// Escape arguments for Windows command line
#ifdef _WIN32
void openjtalk_escape_windows_arg(const char* src, char* dst, size_t dst_size);
#endif

// Validate that a command is safe to execute
int openjtalk_validate_command(const char* command);

#ifdef __cplusplus
}
#endif

#endif // OPENJTALK_SECURITY_H