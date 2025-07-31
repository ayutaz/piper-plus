#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include "openjtalk_security.h"

// Check if a path contains potentially dangerous characters
int openjtalk_is_safe_path(const char* path) {
    if (!path) return 0;
    
    // Check for common command injection characters
    // Note: Parentheses are allowed as they appear in valid paths like "Program Files (x86)"
#ifdef _WIN32
    // On Windows, backslash is a valid path separator
    const char* dangerous_chars = ";|&<>`${}[]!";
#else
    const char* dangerous_chars = ";|&<>`${}[]!\\";
#endif
    
    for (const char* p = path; *p; p++) {
        if (strchr(dangerous_chars, *p)) {
            return 0;
        }
        
        // Also reject control characters
        if (iscntrl(*p) && *p != '\t' && *p != '\n' && *p != '\r') {
            return 0;
        }
    }
    
    // Check for dangerous patterns
    if (strstr(path, "..")) return 0;  // Path traversal
#ifndef _WIN32
    // On Unix, double slash is suspicious
    if (strstr(path, "//")) return 0;  // Double slash
#endif
    
    return 1;
}

// Escape a string for use in shell commands (Windows)
#ifdef _WIN32
void openjtalk_escape_windows_arg(const char* src, char* dst, size_t dst_size) {
    if (!src || !dst || dst_size == 0) return;
    
    size_t dst_pos = 0;
    dst[0] = '\0';
    
    // Add opening quote
    if (dst_pos < dst_size - 1) {
        dst[dst_pos++] = '"';
    }
    
    for (const char* p = src; *p && dst_pos < dst_size - 2; p++) {
        if (*p == '"') {
            // Escape quotes by doubling them
            if (dst_pos < dst_size - 3) {
                dst[dst_pos++] = '"';
                dst[dst_pos++] = '"';
            }
        } else if (*p == '\\') {
            // Count consecutive backslashes
            const char* bs_start = p;
            while (*p == '\\') p++;
            size_t bs_count = p - bs_start;
            p--; // Back up one since loop will increment
            
            // If backslashes are followed by a quote, double them
            if (*(p + 1) == '"') {
                bs_count *= 2;
            }
            
            // Add backslashes
            for (size_t i = 0; i < bs_count && dst_pos < dst_size - 2; i++) {
                dst[dst_pos++] = '\\';
            }
        } else {
            dst[dst_pos++] = *p;
        }
    }
    
    // Add closing quote
    if (dst_pos < dst_size - 1) {
        dst[dst_pos++] = '"';
    }
    
    dst[dst_pos] = '\0';
}
#endif

// Validate that a command is safe to execute
int openjtalk_validate_command(const char* command) {
    if (!command) return 0;
    
    // Check for command chaining attempts
    const char* dangerous_patterns[] = {
        "&&", "||", ";", "|", 
        "$(", "`", 
        ">", "<", ">>", "<<",
        "\n", "\r",
        NULL
    };
    
    for (int i = 0; dangerous_patterns[i]; i++) {
        if (strstr(command, dangerous_patterns[i])) {
            return 0;
        }
    }
    
    return 1;
}