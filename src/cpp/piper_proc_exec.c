// Implementation of argv-based process spawn helpers (see piper_proc_exec.h).
//
// Why this exists: every existing call site that builds a shell-quoted command
// string and passes it to system()/popen() trips CodeQL alerts
// (cpp/command-line-injection, cpp/uncontrolled-process-operation), even when
// the input is validated upstream by piper_is_safe_command_string(), because
// CodeQL's taint tracker does not know that custom validator. Replacing those
// call sites with argv-based spawn fully eliminates shell parsing — there is
// no shell process at all — so the alerts stop firing for the right reason.

#include "piper_proc_exec.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__APPLE__)
#include <TargetConditionals.h>
#endif

#if defined(__APPLE__) && \
    (TARGET_OS_IPHONE || TARGET_OS_TV || TARGET_OS_WATCH || \
     (defined(TARGET_OS_VISION) && TARGET_OS_VISION))
// Apple-embedded App Sandbox forbids spawning external processes.
#define PIPER_PROC_EXEC_DISABLED 1
#endif

#ifdef _WIN32

#include <process.h>
#include <io.h>

int piper_proc_exec_supported(void) { return 1; }

int piper_run_argv(const char* const argv[]) {
    if (!argv || !argv[0]) {
        return -1;
    }
    intptr_t rc = _spawnvp(_P_WAIT, argv[0], (char* const*)argv);
    if (rc == -1) {
        return -1;
    }
    return (int)rc;
}

int piper_capture_argv(const char* const argv[],
                       char* out_buf,
                       size_t out_size,
                       size_t* bytes_read) {
    if (!argv || !argv[0] || !out_buf || out_size == 0) {
        return -1;
    }
    // Build a quoted argv string for _popen — _popen still uses cmd.exe so
    // we must quote each element. The same allow-list validation that the
    // legacy popen() callers already perform upstream still applies. The
    // alternative (_pipe + _spawnvp + _read) is preferred but more involved;
    // tracked as a follow-up since the Windows callers are limited to
    // checksum capture which is bounded in size and content.
    char cmd[2048];
    cmd[0] = '\0';
    size_t pos = 0;
    for (size_t i = 0; argv[i]; i++) {
        size_t len = strlen(argv[i]);
        // 4 bytes overhead per arg for surrounding quotes + space + NUL
        if (pos + len + 4 >= sizeof(cmd)) {
            return -1;
        }
        if (i > 0) cmd[pos++] = ' ';
        cmd[pos++] = '"';
        memcpy(cmd + pos, argv[i], len);
        pos += len;
        cmd[pos++] = '"';
        cmd[pos] = '\0';
    }
    FILE* fp = _popen(cmd, "r");
    if (!fp) {
        return -1;
    }
    size_t total = 0;
    size_t n = fread(out_buf, 1, out_size - 1, fp);
    total = n;
    out_buf[total] = '\0';
    int rc = _pclose(fp);
    if (bytes_read) *bytes_read = total;
    return rc == 0 ? 0 : -1;
}

#elif defined(PIPER_PROC_EXEC_DISABLED)

int piper_proc_exec_supported(void) { return 0; }

int piper_run_argv(const char* const argv[]) {
    (void)argv;
    errno = ENOSYS;
    return -1;
}

int piper_capture_argv(const char* const argv[],
                       char* out_buf,
                       size_t out_size,
                       size_t* bytes_read) {
    (void)argv; (void)out_buf; (void)out_size;
    if (bytes_read) *bytes_read = 0;
    errno = ENOSYS;
    return -1;
}

#else // POSIX

#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;

int piper_proc_exec_supported(void) { return 1; }

int piper_run_argv(const char* const argv[]) {
    if (!argv || !argv[0]) {
        return -1;
    }
    pid_t pid;
    int rc = posix_spawnp(&pid, argv[0], NULL, NULL,
                          (char* const*)argv, environ);
    if (rc != 0) {
        errno = rc;
        return -1;
    }
    int status = 0;
    if (waitpid(pid, &status, 0) == -1) {
        return -1;
    }
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    return -1;
}

int piper_capture_argv(const char* const argv[],
                       char* out_buf,
                       size_t out_size,
                       size_t* bytes_read) {
    if (!argv || !argv[0] || !out_buf || out_size == 0) {
        if (bytes_read) *bytes_read = 0;
        return -1;
    }
    int pipefd[2];
    if (pipe(pipefd) != 0) {
        if (bytes_read) *bytes_read = 0;
        return -1;
    }

    posix_spawn_file_actions_t actions;
    if (posix_spawn_file_actions_init(&actions) != 0) {
        close(pipefd[0]);
        close(pipefd[1]);
        if (bytes_read) *bytes_read = 0;
        return -1;
    }
    // Redirect child's stdout to the write end of the pipe and close the
    // read end (the child should not see it).
    posix_spawn_file_actions_addclose(&actions, pipefd[0]);
    posix_spawn_file_actions_adddup2(&actions, pipefd[1], 1);
    posix_spawn_file_actions_addclose(&actions, pipefd[1]);

    pid_t pid;
    int rc = posix_spawnp(&pid, argv[0], &actions, NULL,
                          (char* const*)argv, environ);
    posix_spawn_file_actions_destroy(&actions);
    close(pipefd[1]); // parent closes write end

    if (rc != 0) {
        close(pipefd[0]);
        if (bytes_read) *bytes_read = 0;
        errno = rc;
        return -1;
    }

    size_t total = 0;
    while (total < out_size - 1) {
        ssize_t n = read(pipefd[0], out_buf + total, out_size - 1 - total);
        if (n <= 0) break;
        total += (size_t)n;
    }
    out_buf[total] = '\0';
    close(pipefd[0]);
    if (bytes_read) *bytes_read = total;

    int status = 0;
    if (waitpid(pid, &status, 0) == -1) {
        return -1;
    }
    if (WIFEXITED(status) && WEXITSTATUS(status) == 0) {
        return 0;
    }
    return -1;
}

#endif // platform branch
